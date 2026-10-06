"""
FlightPulse Intelligence Materialization Module.
Persists deterministic flight delay intelligence results into the PostgreSQL database
table `flight_delay_intelligence` for high-performance reporting and Power BI consumption.
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Optional
from psycopg2.extensions import connection

from pipeline.config import config
from pipeline.database import get_db_connection
from pipeline.intelligence.analyzer import analyze_all_flights

logger = logging.getLogger("flightpulse.intelligence.materialize")


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS flight_delay_intelligence (
    flight_id BIGINT PRIMARY KEY REFERENCES flights(id) ON DELETE CASCADE,
    flight_number VARCHAR(10) NOT NULL,
    primary_candidate_cause VARCHAR(100) NOT NULL,
    confidence_level VARCHAR(20) NOT NULL,
    confidence_score NUMERIC(4,2) NOT NULL,
    primary_signal VARCHAR(150),
    reported_delay_category VARCHAR(50),
    is_on_time BOOLEAN NOT NULL DEFAULT FALSE,
    explanation_summary TEXT NOT NULL,
    supporting_evidence_count INT NOT NULL DEFAULT 0,
    weather_evidence TEXT,
    disruption_evidence TEXT,
    flight_event_evidence TEXT,
    all_evidence_summary TEXT,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fdi_primary_cause ON flight_delay_intelligence (primary_candidate_cause);
CREATE INDEX IF NOT EXISTS idx_fdi_confidence ON flight_delay_intelligence (confidence_level);
CREATE INDEX IF NOT EXISTS idx_fdi_flight_num ON flight_delay_intelligence (flight_number);
"""


UPSERT_SQL = """
INSERT INTO flight_delay_intelligence (
    flight_id,
    flight_number,
    primary_candidate_cause,
    confidence_level,
    confidence_score,
    primary_signal,
    reported_delay_category,
    is_on_time,
    explanation_summary,
    supporting_evidence_count,
    weather_evidence,
    disruption_evidence,
    flight_event_evidence,
    all_evidence_summary,
    evaluated_at
) VALUES (
    %(flight_id)s,
    %(flight_number)s,
    %(primary_candidate_cause)s,
    %(confidence_level)s,
    %(confidence_score)s,
    %(primary_signal)s,
    %(reported_delay_category)s,
    %(is_on_time)s,
    %(explanation_summary)s,
    %(supporting_evidence_count)s,
    %(weather_evidence)s,
    %(disruption_evidence)s,
    %(flight_event_evidence)s,
    %(all_evidence_summary)s,
    CURRENT_TIMESTAMP
)
ON CONFLICT (flight_id) DO UPDATE SET
    flight_number = EXCLUDED.flight_number,
    primary_candidate_cause = EXCLUDED.primary_candidate_cause,
    confidence_level = EXCLUDED.confidence_level,
    confidence_score = EXCLUDED.confidence_score,
    primary_signal = EXCLUDED.primary_signal,
    reported_delay_category = EXCLUDED.reported_delay_category,
    is_on_time = EXCLUDED.is_on_time,
    explanation_summary = EXCLUDED.explanation_summary,
    supporting_evidence_count = EXCLUDED.supporting_evidence_count,
    weather_evidence = EXCLUDED.weather_evidence,
    disruption_evidence = EXCLUDED.disruption_evidence,
    flight_event_evidence = EXCLUDED.flight_event_evidence,
    all_evidence_summary = EXCLUDED.all_evidence_summary,
    evaluated_at = CURRENT_TIMESTAMP;
"""


def materialize_intelligence(conn: Optional[connection] = None) -> int:
    """
    Execute intelligence analysis across all flights in PostgreSQL and persist
    structured attribution results to the `flight_delay_intelligence` table.
    
    Returns:
        Number of flights materialized.
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()

        results = analyze_all_flights(conn=conn)
        logger.info("Materializing intelligence results for %d flights...", len(results))

        records_upserted = 0
        with conn.cursor() as cur:
            for r in results:
                top_candidate = r.candidates[0] if r.candidates else None
                top_score = top_candidate.score if top_candidate else 0.0
                top_conf = (
                    top_candidate.confidence.value
                    if top_candidate
                    else ("N/A" if r.is_on_time else "INSUFFICIENT")
                )
                top_signal = top_candidate.primary_signal if top_candidate else ""

                all_ev = [ev for c in r.candidates for ev in c.evidence]
                weather_ev = [
                    ev for ev in all_ev
                    if any(k in ev.lower() for k in ["weather", "thunderstorm", "wind", "visibility", "metar", "rain", "gust"])
                ]
                disrupt_ev = [
                    ev for ev in all_ev
                    if any(k in ev.lower() for k in ["faa", "ground stop", "ground delay", "nas", "atc", "closure"])
                ]
                flight_ev = [
                    ev for ev in all_ev
                    if any(k in ev.lower() for k in ["dispatch", "gate", "turnaround", "crew", "maintenance"])
                ]

                data = {
                    "flight_id": r.flight_id,
                    "flight_number": r.flight_number,
                    "primary_candidate_cause": r.primary_candidate,
                    "confidence_level": top_conf,
                    "confidence_score": round(top_score, 2),
                    "primary_signal": top_signal,
                    "reported_delay_category": r.reported_delay_category,
                    "is_on_time": r.is_on_time,
                    "explanation_summary": r.explanation_summary,
                    "supporting_evidence_count": len(all_ev),
                    "weather_evidence": " \u2022 " + "\n \u2022 ".join(weather_ev) if weather_ev else None,
                    "disruption_evidence": " \u2022 " + "\n \u2022 ".join(disrupt_ev) if disrupt_ev else None,
                    "flight_event_evidence": " \u2022 " + "\n \u2022 ".join(flight_ev) if flight_ev else None,
                    "all_evidence_summary": " \u2022 " + "\n \u2022 ".join(all_ev) if all_ev else None,
                }

                cur.execute(UPSERT_SQL, data)
                records_upserted += 1

        conn.commit()
        logger.info("Successfully materialized %d intelligence records.", records_upserted)
        return records_upserted
    finally:
        if close_conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    count = materialize_intelligence()
    print(f"Intelligence materialization complete: {count} records stored.")
