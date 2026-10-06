"""
Chronological disruption timeline routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extensions import connection

from app.database import get_db
from app.schemas.timeline import FlightTimelineResponse
from app.services.timeline_service import build_flight_timeline

router = APIRouter(prefix="/flights", tags=["Timeline"])


@router.get("/{flight_id}/timeline", response_model=FlightTimelineResponse)
def get_timeline_for_flight(
    flight_id: int,
    conn: connection = Depends(get_db),
) -> FlightTimelineResponse:
    """
    Retrieve an ordered chronological timeline of factual events for a flight.
    Includes schedule milestones, flight events, weather observations, and disruption windows.
    """
    timeline = build_flight_timeline(conn, flight_id)
    if not timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flight with ID {flight_id} was not found.",
        )
    return timeline
