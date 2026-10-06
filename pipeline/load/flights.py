"""
Flight load module for FlightPulse.
Handles parameterized, idempotent PostgreSQL upserts with dry-run support and metric reporting.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List
from psycopg2.extensions import connection

from pipeline.transform.flights import TransformedFlight

logger = logging.getLogger("flightpulse.load")


@dataclass
class LoadMetrics:
    """Execution metrics from database loading."""
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "dry_run": self.dry_run,
        }


UPSERT_SCHEDULED_FLIGHT_SQL = """
INSERT INTO flights (
    flight_number,
    airline_id,
    origin_airport_id,
    destination_airport_id,
    flight_date,
    scheduled_departure,
    actual_departure,
    scheduled_arrival,
    actual_arrival,
    status,
    departure_delay_minutes,
    arrival_delay_minutes,
    delay_category,
    tail_number,
    aircraft_type,
    distance_miles,
    data_source,
    source_record_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (airline_id, flight_number, scheduled_departure)
DO UPDATE SET
    actual_departure = EXCLUDED.actual_departure,
    actual_arrival = EXCLUDED.actual_arrival,
    status = EXCLUDED.status,
    departure_delay_minutes = EXCLUDED.departure_delay_minutes,
    arrival_delay_minutes = EXCLUDED.arrival_delay_minutes,
    delay_category = COALESCE(EXCLUDED.delay_category, flights.delay_category),
    tail_number = COALESCE(EXCLUDED.tail_number, flights.tail_number),
    aircraft_type = COALESCE(EXCLUDED.aircraft_type, flights.aircraft_type),
    distance_miles = COALESCE(EXCLUDED.distance_miles, flights.distance_miles),
    updated_at = CURRENT_TIMESTAMP
RETURNING (xmax = 0) AS is_inserted;
"""

UPSERT_LIVE_TELEMETRY_SQL = """
INSERT INTO flights (
    flight_number,
    airline_id,
    origin_airport_id,
    destination_airport_id,
    flight_date,
    scheduled_departure,
    actual_departure,
    scheduled_arrival,
    actual_arrival,
    status,
    departure_delay_minutes,
    arrival_delay_minutes,
    delay_category,
    tail_number,
    aircraft_type,
    distance_miles,
    data_source,
    source_record_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (tail_number, actual_departure) WHERE data_source = 'OPENSKY_LIVE' AND tail_number IS NOT NULL AND actual_departure IS NOT NULL
DO UPDATE SET
    actual_arrival = EXCLUDED.actual_arrival,
    status = EXCLUDED.status,
    distance_miles = COALESCE(EXCLUDED.distance_miles, flights.distance_miles),
    updated_at = CURRENT_TIMESTAMP
RETURNING (xmax = 0) AS is_inserted;
"""


def load_flights_to_database(
    conn: connection,
    records: List[TransformedFlight],
    dry_run: bool = False,
) -> LoadMetrics:
    """
    Load normalized flights into PostgreSQL using idempotent upserts.
    
    Args:
        conn: Active psycopg2 database connection
        records: List of TransformedFlight objects to persist
        dry_run: If True, simulates loading without writing to the database

    Returns:
        LoadMetrics detailing rows inserted, updated, and errors.
    """
    metrics = LoadMetrics(dry_run=dry_run)

    if not records:
        logger.info("No transformed flight records to load.")
        return metrics

    if dry_run:
        logger.info("[DRY-RUN] Simulating load of %d records (no database writes)", len(records))
        metrics.inserted = len(records)
        return metrics

    logger.info("Persisting %d flight records to PostgreSQL...", len(records))
    with conn.cursor() as cur:
        for flight in records:
            params = (
                flight.flight_number,
                flight.airline_id,
                flight.origin_airport_id,
                flight.destination_airport_id,
                flight.flight_date,
                flight.scheduled_departure,
                flight.actual_departure,
                flight.scheduled_arrival,
                flight.actual_arrival,
                flight.status,
                flight.departure_delay_minutes,
                flight.arrival_delay_minutes,
                flight.delay_category,
                flight.tail_number,
                flight.aircraft_type,
                flight.distance_miles,
                flight.data_source,
                flight.source_record_id,
            )
            try:
                upsert_query = UPSERT_SCHEDULED_FLIGHT_SQL if flight.scheduled_departure is not None else UPSERT_LIVE_TELEMETRY_SQL
                cur.execute(upsert_query, params)
                res = cur.fetchone()
                if res and res[0] is True:
                    metrics.inserted += 1
                else:
                    metrics.updated += 1
            except Exception as err:
                logger.error("Failed to load flight %s: %s", flight.flight_number, err)
                metrics.errors += 1
                conn.rollback()
                raise

    conn.commit()
    logger.info(
        "Database load complete: %d inserted, %d updated, %d errors",
        metrics.inserted,
        metrics.updated,
        metrics.errors,
    )
    return metrics
