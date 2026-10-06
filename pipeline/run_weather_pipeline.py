"""
FlightPulse Weather Ingestion Pipeline Runner.
Orchestrates Extract -> Validate -> Transform -> Load stages for airport weather observations
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
    load_airports_with_coordinates,
)
from pipeline.extract.weather import extract_airport_weather, load_weather_fixtures
from pipeline.load.weather import WeatherLoadMetrics, load_weather_to_database
from pipeline.transform.weather import transform_weather_records

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("flightpulse.pipeline.weather")


def run_weather_pipeline(
    source_type: str = "fixture",
    airports_list: List[str] = None,
    dry_run: bool = False,
    fixture_path: str = None,
) -> Dict[str, Any]:
    """
    Execute the complete FlightPulse weather ingestion pipeline.
    
    Returns:
        Summary metrics dictionary.
    """
    logger.info("================================================================================")
    logger.info("Starting FlightPulse Weather Ingestion Pipeline [Source: %s | DryRun: %s]", source_type.upper(), dry_run)
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
    # 1. Database Connection & Airport Coordinate Lookups
    # -------------------------------------------------------------------------
    try:
        conn = get_db_connection()
    except Exception as exc:
        logger.error("Failed to connect to PostgreSQL database: %s", exc)
        metrics["errors"] += 1
        return metrics

    try:
        airport_coord_map = load_airports_with_coordinates(conn)
    except Exception as exc:
        logger.error("Failed to load airport coordinates from database: %s", exc)
        metrics["errors"] += 1
        conn.close()
        return metrics

    # -------------------------------------------------------------------------
    # 2. Extract Stage
    # -------------------------------------------------------------------------
    raw_records: List[Dict[str, Any]] = []
    try:
        if source_type.lower() == "openmeteo":
            target_codes = airports_list or ["KORD", "KATL", "KDEN", "KJFK"]
            logger.info("Extracting live Open-Meteo weather for %d target airports: %s", len(target_codes), target_codes)
            for code in target_codes:
                clean_code = code.strip().upper()
                ap_info = airport_coord_map.get(clean_code)
                if not ap_info:
                    logger.warning("Target airport %s not found in database reference catalog. Skipping.", clean_code)
                    metrics["records_skipped"] += 1
                    continue
                try:
                    record = extract_airport_weather(
                        latitude=ap_info["latitude"],
                        longitude=ap_info["longitude"],
                        airport_code=clean_code,
                    )
                    raw_records.append(record)
                except Exception as err:
                    logger.error("Failed to extract weather for airport %s: %s", clean_code, err)
                    metrics["errors"] += 1

        else:
            path = Path(fixture_path) if fixture_path else None
            raw_records = load_weather_fixtures(fixture_path=path)

        metrics["records_extracted"] = len(raw_records)
        logger.info("Stage 1 [EXTRACT]: Extracted %d raw weather records", len(raw_records))
    except Exception as exc:
        logger.error("Stage 1 [EXTRACT] failed: %s", exc)
        metrics["errors"] += 1
        conn.close()
        return metrics

    # -------------------------------------------------------------------------
    # 3. Validate & Transform Stage
    # -------------------------------------------------------------------------
    try:
        report = transform_weather_records(
            raw_records=raw_records,
            airport_coord_map=airport_coord_map,
            data_source="OPEN_METEO" if source_type.lower() == "openmeteo" else "FIXTURE_REPLAY",
        )
        metrics["records_transformed"] = report.total_transformed
        metrics["records_skipped"] += report.total_skipped
        metrics["in_batch_duplicates"] = report.duplicate_count
        logger.info(
            "Stage 2 [TRANSFORM]: %d transformed, %d skipped, %d duplicate(s)",
            report.total_transformed,
            report.total_skipped,
            report.duplicate_count,
        )

        if report.skipped_records:
            logger.warning("Summary of skipped weather records:")
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
        load_result: WeatherLoadMetrics = load_weather_to_database(
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
    logger.info("Weather Pipeline Execution Completed in %.2fs", metrics["duration_seconds"])
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
    parser = argparse.ArgumentParser(description="FlightPulse Weather Ingestion Pipeline Runner")
    parser.add_argument(
        "--source",
        choices=["openmeteo", "fixture"],
        default="fixture",
        help="Weather data source (default: %(default)s)",
    )
    parser.add_argument(
        "--airports",
        default="KORD,KATL,KDEN,KJFK",
        help="Comma-separated airport ICAO codes for live weather extraction (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate extraction and transformation without writing to PostgreSQL",
    )
    parser.add_argument(
        "--fixture-file",
        default=None,
        help="Custom path to raw weather fixture JSON file",
    )

    args = parser.parse_args()

    target_airports = [a.strip() for a in args.airports.split(",") if a.strip()]

    metrics = run_weather_pipeline(
        source_type=args.source,
        airports_list=target_airports,
        dry_run=args.dry_run,
        fixture_path=args.fixture_file,
    )

    if metrics.get("errors", 0) > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
