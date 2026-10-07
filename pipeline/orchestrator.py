"""
FlightPulse Unified Ingestion Orchestrator.
Coordinates concurrent, fault-isolated ingestion across OpenSky, Open-Meteo,
and FAA NAS status feeds while persisting execution telemetry to operations_sync_log.
"""

import concurrent.futures
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from psycopg2.extensions import connection

from pipeline.config import config
from pipeline.database import (
    get_db_connection,
    load_airline_lookup,
    load_airport_lookup,
    load_airports_with_coordinates,
)
from pipeline.extract.flights import (
    OpenSkyExtractionError,
    OpenSkyRateLimitError,
    extract_opensky_flights,
    load_fixture_flights,
)
from pipeline.extract.news import extract_faa_nas_events, load_news_fixtures
from pipeline.extract.weather import extract_airport_weather, load_weather_fixtures
from pipeline.load.flights import load_flights_to_database
from pipeline.load.news import load_news_to_database
from pipeline.load.weather import load_weather_to_database
from pipeline.transform.flights import transform_flight_records
from pipeline.transform.news import transform_news_records
from pipeline.transform.weather import transform_weather_records

logger = logging.getLogger("flightpulse.orchestrator")


@dataclass
class SourceSyncResult:
    """Detailed telemetry result for an individual ingestion source."""
    source_name: str
    status: str  # 'SUCCESS', 'FAILED', 'SKIPPED'
    records_extracted: int = 0
    records_transformed: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_skipped: int = 0
    errors: int = 0
    error_message: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    skip_reasons: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "status": self.status,
            "records_extracted": self.records_extracted,
            "records_transformed": self.records_transformed,
            "records_inserted": self.records_inserted,
            "records_updated": self.records_updated,
            "records_skipped": self.records_skipped,
            "errors": self.errors,
            "error_message": self.error_message,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp.isoformat(),
            "skip_reasons": self.skip_reasons,
        }


@dataclass
class OrchestrationResult:
    """Aggregated result across all orchestrated ingestion branches."""
    overall_status: str  # 'SUCCESS', 'PARTIAL', 'FAILED'
    sources: Dict[str, SourceSyncResult] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp.isoformat(),
        }


def record_sync_log(
    conn: connection,
    sync_source: str,
    sync_status: str,
    records_extracted: int,
    records_inserted: int,
    records_updated: int,
    error_message: Optional[str],
    duration_ms: float,
) -> None:
    """Safely persist an operational sync log entry to PostgreSQL."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO operations_sync_log (
                    sync_source,
                    sync_status,
                    records_extracted,
                    records_inserted,
                    records_updated,
                    error_message,
                    duration_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    sync_source,
                    sync_status,
                    records_extracted,
                    records_inserted,
                    records_updated,
                    error_message,
                    round(duration_ms, 2),
                ),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("Could not persist sync log for %s: %s", sync_source, exc)


def ingest_flights_branch(
    mode: str = "demo",
    airport_icao: str = "KORD",
    lookback_hours: int = 2,
    dry_run: bool = False,
    fixture_path: Optional[str] = None,
    conn: Optional[connection] = None,
) -> SourceSyncResult:
    """
    Ingest flights branch (fault-isolated).
    Mode 'live' extracts from OpenSky and writes data_source='OPENSKY_LIVE'.
    Mode 'demo' loads fixture and preserves existing behavior.
    """
    t0 = time.time()
    source_label = "OPENSKY_LIVE" if mode.lower() == "live" else "DEMO_FLIGHTS"
    res = SourceSyncResult(source_name=source_label, status="FAILED")

    close_conn = False
    if conn is None:
        try:
            conn = get_db_connection()
            close_conn = True
        except Exception as exc:
            res.error_message = f"Database connection failed: {exc}"
            res.duration_ms = (time.time() - t0) * 1000
            return res

    try:
        airport_icao_map, airport_iata_map = load_airport_lookup(conn)
        airline_icao_map, airline_iata_map = load_airline_lookup(conn)

        if mode.lower() == "live":
            now_epoch = int(datetime.now(timezone.utc).timestamp())
            end_epoch = now_epoch - 300
            begin_epoch = end_epoch - min(lookback_hours * 3600, 7200)
            raw_records = extract_opensky_flights(
                airport_icao=airport_icao,
                begin_timestamp=begin_epoch,
                end_timestamp=end_epoch,
            )
            data_source = "OPENSKY_LIVE"
        else:
            raw_records = load_fixture_flights(Path(fixture_path) if fixture_path else None)
            data_source = "FIXTURE_REPLAY"

        res.records_extracted = len(raw_records)

        report = transform_flight_records(
            raw_records=raw_records,
            airport_icao_map=airport_icao_map,
            airport_iata_map=airport_iata_map,
            airline_icao_map=airline_icao_map,
            airline_iata_map=airline_iata_map,
            data_source=data_source,
        )
        res.records_transformed = report.total_transformed
        res.records_skipped = report.total_skipped
        res.skip_reasons = report.skip_reasons

        metrics = load_flights_to_database(conn, report.transformed, dry_run=dry_run)
        res.records_inserted = metrics.inserted
        res.records_updated = metrics.updated
        res.errors = metrics.errors
        res.status = "SUCCESS"

    except OpenSkyRateLimitError as rle:
        logger.warning("Flight ingestion branch rate limited by OpenSky: %s", rle)
        res.status = "RATE_LIMITED"
        res.error_message = str(rle)

    except Exception as exc:
        logger.error("Flight ingestion branch failed: %s", exc)
        res.status = "FAILED"
        res.errors += 1
        res.error_message = str(exc)

    finally:
        res.duration_ms = (time.time() - t0) * 1000
        record_sync_log(
            conn=conn,
            sync_source=source_label,
            sync_status=res.status,
            records_extracted=res.records_extracted,
            records_inserted=res.records_inserted,
            records_updated=res.records_updated,
            error_message=res.error_message,
            duration_ms=res.duration_ms,
        )
        if close_conn:
            conn.close()

    return res


def ingest_weather_branch(
    mode: str = "demo",
    target_airports: Optional[List[str]] = None,
    dry_run: bool = False,
    fixture_path: Optional[str] = None,
    conn: Optional[connection] = None,
) -> SourceSyncResult:
    """
    Ingest weather observations branch (fault-isolated).
    Mode 'live' calls Open-Meteo REST API and writes data_source='OPENMETEO_LIVE'.
    Mode 'demo' loads fixture data.
    """
    t0 = time.time()
    source_label = "OPENMETEO_LIVE" if mode.lower() == "live" else "DEMO_WEATHER"
    res = SourceSyncResult(source_name=source_label, status="FAILED")

    close_conn = False
    if conn is None:
        try:
            conn = get_db_connection()
            close_conn = True
        except Exception as exc:
            res.error_message = f"Database connection failed: {exc}"
            res.duration_ms = (time.time() - t0) * 1000
            return res

    try:
        airport_coord_map = load_airports_with_coordinates(conn)

        raw_records = []
        if mode.lower() == "live":
            airports = target_airports or ["KORD", "KATL", "KDEN", "KJFK"]
            for code in airports:
                ap_info = airport_coord_map.get(code.strip().upper())
                if not ap_info:
                    continue
                try:
                    record = extract_airport_weather(
                        latitude=ap_info["latitude"],
                        longitude=ap_info["longitude"],
                        airport_code=code,
                    )
                    raw_records.append(record)
                except Exception as ap_err:
                    logger.warning("Failed extracting weather for %s: %s", code, ap_err)
            data_source = "OPENMETEO_LIVE"
        else:
            raw_records = load_weather_fixtures(Path(fixture_path) if fixture_path else None)
            data_source = "FIXTURE_REPLAY"

        res.records_extracted = len(raw_records)

        report = transform_weather_records(raw_records, airport_coord_map, data_source=data_source)
        res.records_transformed = report.total_transformed
        res.records_skipped = report.total_skipped

        metrics = load_weather_to_database(conn, report.transformed, dry_run=dry_run)
        res.records_inserted = metrics.inserted
        res.records_updated = metrics.updated
        res.errors = metrics.errors
        res.status = "SUCCESS"

    except Exception as exc:
        logger.error("Weather ingestion branch failed: %s", exc)
        res.status = "FAILED"
        res.errors += 1
        res.error_message = str(exc)

    finally:
        res.duration_ms = (time.time() - t0) * 1000
        record_sync_log(
            conn=conn,
            sync_source=source_label,
            sync_status=res.status,
            records_extracted=res.records_extracted,
            records_inserted=res.records_inserted,
            records_updated=res.records_updated,
            error_message=res.error_message,
            duration_ms=res.duration_ms,
        )
        if close_conn:
            conn.close()

    return res


def ingest_disruptions_branch(
    mode: str = "demo",
    dry_run: bool = False,
    fixture_path: Optional[str] = None,
    conn: Optional[connection] = None,
) -> SourceSyncResult:
    """
    Ingest FAA ATCSCC disruption notices branch (fault-isolated).
    Mode 'live' parses FAA NAS status XML feed and writes data_source='FAA_LIVE'.
    Mode 'demo' loads fixture data.
    """
    t0 = time.time()
    source_label = "FAA_LIVE" if mode.lower() == "live" else "DEMO_FAA"
    res = SourceSyncResult(source_name=source_label, status="FAILED")

    close_conn = False
    if conn is None:
        try:
            conn = get_db_connection()
            close_conn = True
        except Exception as exc:
            res.error_message = f"Database connection failed: {exc}"
            res.duration_ms = (time.time() - t0) * 1000
            return res

    try:
        airport_icao_map, airport_iata_map = load_airport_lookup(conn)
        airline_icao_map, airline_iata_map = load_airline_lookup(conn)
        combined_airports = {**airport_icao_map, **airport_iata_map}
        combined_airlines = {**airline_icao_map, **airline_iata_map}

        if mode.lower() == "live":
            raw_records = extract_faa_nas_events()
            data_source = "FAA_LIVE"
        else:
            raw_records = load_news_fixtures(Path(fixture_path) if fixture_path else None)
            data_source = "FIXTURE_REPLAY"

        res.records_extracted = len(raw_records)

        report = transform_news_records(
            raw_records=raw_records,
            airport_code_map=combined_airports,
            airline_code_map=combined_airlines,
            data_source=data_source,
        )
        res.records_transformed = report.total_transformed
        res.records_skipped = report.total_skipped

        metrics = load_news_to_database(conn, report.transformed, dry_run=dry_run)
        res.records_inserted = metrics.inserted
        res.records_updated = metrics.updated
        res.errors = metrics.errors
        res.status = "SUCCESS"

    except Exception as exc:
        logger.error("FAA disruptions ingestion branch failed: %s", exc)
        res.status = "FAILED"
        res.errors += 1
        res.error_message = str(exc)

    finally:
        res.duration_ms = (time.time() - t0) * 1000
        record_sync_log(
            conn=conn,
            sync_source=source_label,
            sync_status=res.status,
            records_extracted=res.records_extracted,
            records_inserted=res.records_inserted,
            records_updated=res.records_updated,
            error_message=res.error_message,
            duration_ms=res.duration_ms,
        )
        if close_conn:
            conn.close()

    return res


def orchestrate_ingestion(
    mode: str = "demo",
    airport_icao: str = "KORD",
    weather_airports: Optional[List[str]] = None,
    dry_run: bool = False,
    max_workers: int = 3,
) -> OrchestrationResult:
    """
    Execute unified ingestion across OpenSky, Open-Meteo, and FAA branches concurrently.
    Guarantees strict fault isolation: failure in any single source never aborts other branches.
    """
    t0 = time.time()
    logger.info("Starting FlightPulse unified ingestion orchestration [Mode: %s | DryRun: %s]", mode.upper(), dry_run)

    sources_map: Dict[str, SourceSyncResult] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_flights = executor.submit(
            ingest_flights_branch,
            mode=mode,
            airport_icao=airport_icao,
            dry_run=dry_run,
        )
        future_weather = executor.submit(
            ingest_weather_branch,
            mode=mode,
            target_airports=weather_airports,
            dry_run=dry_run,
        )
        future_disruptions = executor.submit(
            ingest_disruptions_branch,
            mode=mode,
            dry_run=dry_run,
        )

        sources_map["flights"] = future_flights.result()
        sources_map["weather"] = future_weather.result()
        sources_map["disruptions"] = future_disruptions.result()

    total_duration_ms = (time.time() - t0) * 1000

    success_count = sum(1 for s in sources_map.values() if s.status == "SUCCESS")
    if success_count == len(sources_map):
        overall = "SUCCESS"
    elif success_count > 0:
        overall = "PARTIAL"
    else:
        overall = "FAILED"

    logger.info(
        "Orchestration completed in %.1fms with status: %s (Success: %d/%d)",
        total_duration_ms,
        overall,
        success_count,
        len(sources_map),
    )

    return OrchestrationResult(
        overall_status=overall,
        sources=sources_map,
        duration_ms=total_duration_ms,
    )
