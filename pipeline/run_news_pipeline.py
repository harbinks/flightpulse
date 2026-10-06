"""
FlightPulse News & Disruption Ingestion Pipeline Runner.
Orchestrates Extract -> Validate -> Transform -> Load stages for aviation operational disruption events
with structured logging and execution metrics.
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from pipeline.config import config
from pipeline.database import (
    get_db_connection,
    load_airline_lookup,
    load_airport_lookup,
)
from pipeline.extract.news import extract_faa_nas_events, load_news_fixtures
from pipeline.load.news import NewsLoadMetrics, load_news_to_database
from pipeline.transform.news import transform_news_records

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("flightpulse.pipeline.news")


def run_news_pipeline(
    source_type: str = "fixture",
    dry_run: bool = False,
    fixture_path: str = None,
) -> Dict[str, Any]:
    """
    Execute the complete FlightPulse news and disruption ingestion pipeline.
    
    Returns:
        Summary metrics dictionary.
    """
    logger.info("================================================================================")
    logger.info("Starting FlightPulse News & Disruption Ingestion Pipeline [Source: %s | DryRun: %s]", source_type.upper(), dry_run)
    logger.info("================================================================================")

    start_time = time.time()
    metrics = {
        "source": source_type,
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

        # Merge lookup dictionaries for flexible code resolution
        combined_airports = {**airport_icao_map, **airport_iata_map}
        combined_airlines = {**airline_icao_map, **airline_iata_map}
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
        if source_type.lower() == "faa":
            logger.info("Extracting live disruption events from FAA ATCSCC NAS status feed")
            raw_records = extract_faa_nas_events()
        else:
            path = Path(fixture_path) if fixture_path else None
            raw_records = load_news_fixtures(fixture_path=path)

        metrics["records_extracted"] = len(raw_records)
        logger.info("Stage 1 [EXTRACT]: Extracted %d raw disruption records", len(raw_records))
    except Exception as exc:
        logger.error("Stage 1 [EXTRACT] failed: %s", exc)
        metrics["errors"] += 1
        conn.close()
        return metrics

    # -------------------------------------------------------------------------
    # 3. Validate & Transform Stage
    # -------------------------------------------------------------------------
    try:
        report = transform_news_records(
            raw_records=raw_records,
            airport_code_map=combined_airports,
            airline_code_map=combined_airlines,
            data_source="FAA_ATCSCC" if source_type.lower() == "faa" else "FIXTURE_REPLAY",
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
            logger.warning("Summary of skipped news records:")
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
        load_result: NewsLoadMetrics = load_news_to_database(
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
    logger.info("News Pipeline Execution Completed in %.2fs", metrics["duration_seconds"])
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
    parser = argparse.ArgumentParser(description="FlightPulse News & Disruption Ingestion Pipeline Runner")
    parser.add_argument(
        "--source",
        choices=["faa", "fixture"],
        default="fixture",
        help="Disruption data source (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate extraction and transformation without writing to PostgreSQL",
    )
    parser.add_argument(
        "--fixture-file",
        default=None,
        help="Custom path to raw news fixture JSON file",
    )

    args = parser.parse_args()

    metrics = run_news_pipeline(
        source_type=args.source,
        dry_run=args.dry_run,
        fixture_path=args.fixture_file,
    )

    if metrics.get("errors", 0) > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
