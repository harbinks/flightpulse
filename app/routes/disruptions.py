"""
Disruption and operational notice routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extensions import connection

from app.database import get_db
from app.schemas.disruptions import FlightDisruptionsResponse
from app.services.flight_service import get_flight_disruptions

router = APIRouter(prefix="/flights", tags=["Disruptions"])


@router.get("/{flight_id}/disruptions", response_model=FlightDisruptionsResponse)
def get_disruptions_for_flight(
    flight_id: int,
    conn: connection = Depends(get_db),
) -> FlightDisruptionsResponse:
    """Retrieve FAA advisories and operational disruptions affecting a flight."""
    disruptions = get_flight_disruptions(conn, flight_id)
    if not disruptions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flight with ID {flight_id} was not found.",
        )
    return disruptions
