"""
Intelligence service integrating the deterministic delay intelligence engine with FastAPI endpoints.
Reuses the existing pipeline intelligence engine without duplicating causal reasoning or scoring logic.
"""

from typing import Optional
from psycopg2.extensions import connection

from app.schemas.intelligence import (
    CandidateCauseItem,
    DelayIntelligenceResponse,
    DelayMetadata,
    PrimaryAttribution,
)
from pipeline.intelligence.analyzer import analyze_flight_delay


def get_flight_intelligence(conn: connection, flight_id: int) -> Optional[DelayIntelligenceResponse]:
    """
    Execute deterministic delay intelligence analysis for a flight.
    
    Args:
        conn: Active psycopg2 database connection
        flight_id: Unique flight identifier

    Returns:
        DelayIntelligenceResponse if flight exists, else None.
    """
    analysis = analyze_flight_delay(flight_id, conn=conn)
    if not analysis:
        return None

    # Determine primary attribution scores
    if analysis.candidates:
        top = analysis.candidates[0]
        primary = PrimaryAttribution(
            category=analysis.primary_candidate,
            score=round(top.score, 2),
            confidence=top.confidence.value,
        )
    else:
        primary = PrimaryAttribution(
            category=analysis.primary_candidate,
            score=0.0,
            confidence="INSUFFICIENT" if not analysis.is_on_time else "HIGH",
        )

    candidates = [
        CandidateCauseItem(
            category=c.category,
            score=round(c.score, 2),
            confidence=c.confidence.value,
            primary_signal=c.primary_signal,
            evidence=c.evidence,
        )
        for c in analysis.candidates
    ]

    flight_meta = {
        "id": analysis.flight_id,
        "flight_number": analysis.flight_number,
        "airline": analysis.airline,
        "origin": analysis.origin,
        "destination": analysis.destination,
        "route": f"{analysis.origin} -> {analysis.destination}",
        "scheduled_departure": analysis.scheduled_departure,
        "actual_departure": analysis.actual_departure,
    }

    delay_meta = DelayMetadata(
        minutes=analysis.departure_delay_minutes,
        arrival_delay_minutes=analysis.departure_delay_minutes,
        reported_category=analysis.reported_delay_category,
        status=analysis.status,
        is_on_time=analysis.is_on_time,
    )

    return DelayIntelligenceResponse(
        flight=flight_meta,
        delay=delay_meta,
        primary_candidate=primary,
        candidates=candidates,
        explanation_summary=analysis.explanation_summary,
    )
