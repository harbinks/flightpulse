"""
High-level intelligence analyzer module for FlightPulse.
Provides programmatic entrypoints for analyzing individual flights or all operational flights.
"""

import logging
from typing import List, Optional, Union
from psycopg2.extensions import connection

from pipeline.database import get_db_connection
from pipeline.intelligence.candidate_generation import (
    DelayAnalysisResult,
    generate_candidates_for_flight,
)
from pipeline.intelligence.evidence import collect_flight_evidence

logger = logging.getLogger("flightpulse.intelligence.analyzer")


def analyze_flight_delay(
    flight_ref: Union[int, str],
    conn: Optional[connection] = None,
) -> Optional[DelayAnalysisResult]:
    """
    Perform deterministic causal delay analysis for a single flight.
    
    Args:
        flight_ref: Flight ID (int) or Flight Number (e.g. 'UA415')
        conn: Optional active psycopg2 database connection

    Returns:
        DelayAnalysisResult if flight exists, else None.
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        bundle = collect_flight_evidence(conn, flight_ref)
        if not bundle:
            logger.warning("No operational flight record found for reference: %s", flight_ref)
            return None

        result = generate_candidates_for_flight(bundle)
        return result
    finally:
        if close_conn:
            conn.close()


def analyze_all_flights(
    conn: Optional[connection] = None,
    delayed_only: bool = False,
) -> List[DelayAnalysisResult]:
    """
    Perform deterministic causal delay analysis for all flights in the database.
    
    Args:
        conn: Optional active psycopg2 database connection
        delayed_only: If True, only analyzes flights with departure delay > 15 minutes.

    Returns:
        List of DelayAnalysisResult objects.
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        with conn.cursor() as cur:
            if delayed_only:
                cur.execute("SELECT id FROM flights WHERE departure_delay_minutes > 15 ORDER BY scheduled_departure DESC;")
            else:
                cur.execute("SELECT id FROM flights ORDER BY scheduled_departure DESC;")
            flight_ids = [row[0] for row in cur.fetchall()]

        logger.info("Running intelligence analysis across %d flights (delayed_only=%s)", len(flight_ids), delayed_only)
        results: List[DelayAnalysisResult] = []
        for fid in flight_ids:
            res = analyze_flight_delay(fid, conn=conn)
            if res:
                results.append(res)

        return results
    finally:
        if close_conn:
            conn.close()
