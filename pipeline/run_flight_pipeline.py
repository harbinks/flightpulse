"""
FlightPulse Flight Ingestion Pipeline Runner.
Orchestrates Extract -> Validate -> Transform -> Load stages with structured logging and metrics.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pipeline.config import config
from pipeline.database import (
    get_db_connection,
    load_airline_lookup,
    load_airport_lookup,
)
from pipeline.extract.flights import extract_opensky_flights, load_fixture_flights
from pipeline.load.flights import LoadMetrics, load_flights_to_database
from pipeline.transform.flights import transform_flight_records

# Configure structured root logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("flightpulse.pipeline")


def run_pipeline(
    source_type: str = "fixture",
    airport_icao: str = "KORD",
    lookback_hours: int = 2,
    dry_run: bool = False,
    fixture_path: str = None,
) -> Dict[str, Any]:
    """
    Execute the complete FlightPulse flight ingestion pipeline.
    
    Returns:
        Summary metrics dictionary.
    """
    logger.info("================================================================================")
    logger.info("Starting FlightPulse Ingestion Pipeline [Source: %s | DryRun: %s]", source_type.upper(), dry_run)
    logger.info("================================================================================")

    start_time = time.time()
    metrics = {
        "source": source_type,
        "airport": airport_icao,
        "dry_run": dry_run,
        "records_extracted": 0,
        "records_transformed": 0,
        "records_inserted": 0,
        "records_updated": 0,
        "records_skipped": 0,
        "in_batch_duplicates": 0,
        "errors": 0,
        "duration_seconds": 0.0,
    }

    # -------------------------------------------------------------------------
    # 1. Database Connection & Lookup Pre-caching
    # -------------------------------------------------------------------------
    try:
        conn = get_db_connection()
    except Exception as exc:
        logger.error("Failed to connect to PostgreSQL database: %s", exc)
        metrics["errors"] += 1
        return metrics

    try:
        airport_icao_map, airport_iata_map = load_airport_lookup(conn)
        airline_icao_map, airline_iata_map = load_airline_lookup(conn)
    except Exception as exc:
        logger.error("Failed to load reference lookups from database: %s", exc)
        metrics["errors"] += 1
        conn.close()
        return metrics

    # -------------------------------------------------------------------------
    # 2. Extract Stage
    # -------------------------------------------------------------------------
    raw_records: List[Dict[str, Any]] = []
    try:
        if source_type.lower() == "opensky":
            now_epoch = int(datetime.now(timezone.utc).timestamp())
            # OpenSky anonymous access allows querying data within the most recent 2 hours (up to 7200s).
            # Authenticated users with credentials in .env can query historical flights up to 30 days.
            if config.opensky.username and config.opensky.password:
                end_epoch = now_epoch - 3600
                window_seconds = min(lookback_hours * 3600, 7200)
                begin_epoch = end_epoch - window_seconds
            else:
                end_epoch = now_epoch - 300
                window_seconds = min(lookback_hours * 3600, 6800)
                begin_epoch = end_epoch - window_seconds

            logger.info("Extracting live OpenSky flights for %s (time window: %s - %s)", airport_icao, begin_epoch, end_epoch)
            raw_records = extract_opensky_flights(
                airport_icao=airport_icao,
                begin_timestamp=begin_epoch,
                end_timestamp=end_epoch,
            )
        else:
            path = Path(fixture_path) if fixture_path else None
            raw_records = load_fixture_flights(fixture_path=path)

        metrics["records_extracted"] = len(raw_records)
        logger.info("Stage 1 [EXTRACT]: Extracted %d raw records", len(raw_records))
    except Exception as exc:
        logger.error("Stage 1 [EXTRACT] failed: %s", exc)
        metrics["errors"] += 1
        conn.close()
        return metrics

    # -------------------------------------------------------------------------
    # 3. Validate & Transform Stage
    # -------------------------------------------------------------------------
    try:
        report = transform_flight_records(
            raw_records=raw_records,
            airport_icao_map=airport_icao_map,
            airport_iata_map=airport_iata_map,
            airline_icao_map=airline_icao_map,
            airline_iata_map=airline_iata_map,
            data_source="OPENSKY_LIVE" if source_type.lower() == "opensky" else "FIXTURE_REPLAY",
        )
        metrics["records_transformed"] = report.total_transformed
        metrics["records_skipped"] = report.total_skipped
        metrics["in_batch_duplicates"] = report.duplicate_count
        logger.info(
            "Stage 2 [TRANSFORM]: %d transformed, %d skipped, %d duplicate(s)",
            report.total_transformed,
            report.total_skipped,
            report.duplicate_count,
        )

        if report.skipped_records:
            logger.warning("Summary of skipped records:")
            for sk in report.skipped_records:
                logger.warning("  - Reason: %s | Detail: %s", sk.get("reason"), {k: v for k, v in sk.items() if k not in ('raw', 'reason')})

    except Exception as exc:
        logger.error("Stage 2 [TRANSFORM] failed: %s", exc)
        metrics["errors"] += 1
        conn.close()
        return metrics

    # -------------------------------------------------------------------------
    # 4. Load Stage (Idempotent Upsert)
    # -------------------------------------------------------------------------
    try:
        load_result: LoadMetrics = load_flights_to_database(
            conn=conn,
            records=report.transformed,
            dry_run=dry_run,
        )
        metrics["records_inserted"] = load_result.inserted
        metrics["records_updated"] = load_result.updated
        metrics["errors"] += load_result.errors
        logger.info(
            "Stage 3 [LOAD]: %d inserted, %d updated, %d errors (dry_run=%s)",
            load_result.inserted,
            load_result.updated,
            load_result.errors,
            dry_run,
        )
    except Exception as exc:
        logger.error("Stage 3 [LOAD] failed: %s", exc)
        metrics["errors"] += 1
    finally:
        conn.close()

    metrics["duration_seconds"] = round(time.time() - start_time, 2)
    logger.info("================================================================================")
    logger.info("Pipeline Execution Completed in %.2fs", metrics["duration_seconds"])
    logger.info(
        "Final Metrics -> Extracted: %d | Transformed: %d | Inserted: %d | Updated: %d | Skipped: %d | Errors: %d",
        metrics["records_extracted"],
        metrics["records_transformed"],
        metrics["records_inserted"],
        metrics["records_updated"],
        metrics["records_skipped"],
        metrics["errors"],
    )
    logger.info("================================================================================")
    return metrics


def main():
    parser = argparse.ArgumentParser(description="FlightPulse Flight Ingestion Pipeline Runner")
    parser.add_argument(
        "--source",
        choices=["opensky", "fixture"],
        default=config.data_source,
        help="Data extraction source (default: %(default)s)",
    )
    parser.add_argument(
        "--airport",
        default="KORD",
        help="4-letter ICAO airport code for live extraction (default: KORD)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=2,
        help="Time window in hours for OpenSky extraction (max 2, default: 2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate extraction and transformation without writing to PostgreSQL",
    )
    parser.add_argument(
        "--fixture-file",
        default=None,
        help="Custom path to raw flight fixture JSON file",
    )

    args = parser.parse_args()

    metrics = run_pipeline(
        source_type=args.source,
        airport_icao=args.airport,
        lookback_hours=args.hours,
        dry_run=args.dry_run,
        fixture_path=args.fixture_file,
    )

    if metrics.get("errors", 0) > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
