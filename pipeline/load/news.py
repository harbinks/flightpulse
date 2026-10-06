"""
News and disruption load module for FlightPulse.
Handles parameterized, idempotent persistence of news/disruption events into the
`news_events` PostgreSQL table without requiring schema changes.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List
from psycopg2.extensions import connection

from pipeline.transform.news import TransformedNewsEvent

logger = logging.getLogger("flightpulse.load.news")


@dataclass
class NewsLoadMetrics:
    """Execution metrics from database loading of news events."""
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


CHECK_EXISTING_NEWS_SQL = """
SELECT id FROM news_events
WHERE data_source = %s AND source_record_id = %s
LIMIT 1;
"""

UPDATE_NEWS_SQL = """
UPDATE news_events SET
    title = %s,
    summary = %s,
    source = %s,
    url = %s,
    event_type = %s,
    severity = %s,
    airport_id = %s,
    airline_id = %s,
    start_time = %s,
    end_time = %s,
    updated_at = CURRENT_TIMESTAMP
WHERE id = %s;
"""

INSERT_NEWS_SQL = """
INSERT INTO news_events (
    title,
    summary,
    source,
    url,
    event_type,
    severity,
    airport_id,
    airline_id,
    start_time,
    end_time,
    data_source,
    source_record_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
"""


def load_news_to_database(
    conn: connection,
    records: List[TransformedNewsEvent],
    dry_run: bool = False,
) -> NewsLoadMetrics:
    """
    Load normalized disruption events into PostgreSQL using idempotent upserts.
    
    Args:
        conn: Active psycopg2 database connection
        records: List of TransformedNewsEvent records to persist
        dry_run: If True, simulates loading without writing to the database

    Returns:
        NewsLoadMetrics detailing rows inserted, updated, and errors.
    """
    metrics = NewsLoadMetrics(dry_run=dry_run)

    if not records:
        logger.info("No transformed news records to load.")
        return metrics

    if dry_run:
        logger.info("[DRY-RUN] Simulating load of %d news events (no database writes)", len(records))
        metrics.inserted = len(records)
        return metrics

    logger.info("Persisting %d news/disruption events to PostgreSQL...", len(records))
    with conn.cursor() as cur:
        for event in records:
            try:
                # 1. Check if event exists by data_source and source_record_id
                cur.execute(CHECK_EXISTING_NEWS_SQL, (event.data_source, event.source_record_id))
                row = cur.fetchone()

                if row:
                    # Update existing record
                    existing_id = row[0]
                    update_params = (
                        event.title,
                        event.summary,
                        event.source,
                        event.url,
                        event.event_type,
                        event.severity,
                        event.airport_id,
                        event.airline_id,
                        event.start_time,
                        event.end_time,
                        existing_id,
                    )
                    cur.execute(UPDATE_NEWS_SQL, update_params)
                    metrics.updated += 1
                else:
                    # Insert new record
                    insert_params = (
                        event.title,
                        event.summary,
                        event.source,
                        event.url,
                        event.event_type,
                        event.severity,
                        event.airport_id,
                        event.airline_id,
                        event.start_time,
                        event.end_time,
                        event.data_source,
                        event.source_record_id,
                    )
                    cur.execute(INSERT_NEWS_SQL, insert_params)
                    metrics.inserted += 1

            except Exception as err:
                logger.error("Failed to load news event '%s': %s", event.title, err)
                metrics.errors += 1
                conn.rollback()
                raise

    conn.commit()
    logger.info(
        "Database news load complete: %d inserted, %d updated, %d errors",
        metrics.inserted,
        metrics.updated,
        metrics.errors,
    )
    return metrics
