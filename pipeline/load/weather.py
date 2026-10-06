"""
Weather load module for FlightPulse.
Performs parameterized, idempotent PostgreSQL upserts on `weather_observations`
using the `(airport_id, observation_time)` unique constraint.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List
from psycopg2.extensions import connection

from pipeline.transform.weather import TransformedWeather

logger = logging.getLogger("flightpulse.load.weather")


@dataclass
class WeatherLoadMetrics:
    """Execution metrics from loading weather observations into PostgreSQL."""
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


UPSERT_WEATHER_SQL = """
INSERT INTO weather_observations (
    airport_id,
    observation_time,
    temperature_c,
    dewpoint_c,
    wind_speed_knots,
    wind_gust_knots,
    wind_direction_deg,
    visibility_miles,
    altimeter_inhg,
    condition_code,
    raw_metar,
    data_source,
    source_record_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (airport_id, observation_time)
DO UPDATE SET
    temperature_c = EXCLUDED.temperature_c,
    dewpoint_c = EXCLUDED.dewpoint_c,
    wind_speed_knots = EXCLUDED.wind_speed_knots,
    wind_gust_knots = EXCLUDED.wind_gust_knots,
    wind_direction_deg = EXCLUDED.wind_direction_deg,
    visibility_miles = EXCLUDED.visibility_miles,
    altimeter_inhg = EXCLUDED.altimeter_inhg,
    condition_code = EXCLUDED.condition_code,
    raw_metar = EXCLUDED.raw_metar,
    ingested_at = CURRENT_TIMESTAMP
RETURNING (xmax = 0) AS is_inserted;
"""


def load_weather_to_database(
    conn: connection,
    records: List[TransformedWeather],
    dry_run: bool = False,
) -> WeatherLoadMetrics:
    """
    Load normalized weather observations into PostgreSQL using idempotent upserts.
    
    Args:
        conn: Active psycopg2 database connection
        records: List of TransformedWeather records to persist
        dry_run: If True, simulates loading without writing to the database

    Returns:
        WeatherLoadMetrics detailing rows inserted, updated, and errors.
    """
    metrics = WeatherLoadMetrics(dry_run=dry_run)

    if not records:
        logger.info("No transformed weather records to load.")
        return metrics

    if dry_run:
        logger.info("[DRY-RUN] Simulating load of %d weather records (no database writes)", len(records))
        metrics.inserted = len(records)
        return metrics

    logger.info("Persisting %d weather records to PostgreSQL...", len(records))
    with conn.cursor() as cur:
        for wx in records:
            params = (
                wx.airport_id,
                wx.observation_time,
                wx.temperature_c,
                wx.dewpoint_c,
                wx.wind_speed_knots,
                wx.wind_gust_knots,
                wx.wind_direction_deg,
                wx.visibility_miles,
                wx.altimeter_inhg,
                wx.condition_code,
                wx.raw_metar,
                wx.data_source,
                wx.source_record_id,
            )
            try:
                cur.execute(UPSERT_WEATHER_SQL, params)
                res = cur.fetchone()
                if res and res[0] is True:
                    metrics.inserted += 1
                else:
                    metrics.updated += 1
            except Exception as err:
                logger.error("Failed to load weather observation for airport %d at %s: %s", wx.airport_id, wx.observation_time, err)
                metrics.errors += 1
                conn.rollback()
                raise

    conn.commit()
    logger.info(
        "Database weather load complete: %d inserted, %d updated, %d errors",
        metrics.inserted,
        metrics.updated,
        metrics.errors,
    )
    return metrics
