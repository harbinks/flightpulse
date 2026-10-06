"""
Flight search and retrieval routes.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg2.extensions import connection

from app.database import get_db
from app.schemas.flights import FlightDetailResponse, FlightListResponse
from app.services.flight_service import get_flight_by_id, search_flights

router = APIRouter(prefix="/flights", tags=["Flights"])


@router.get("", response_model=FlightListResponse)
def list_flights(
    airline: Optional[str] = Query(None, description="Airline IATA or ICAO (e.g. DL, UA)"),
    flight_number: Optional[str] = Query(None, description="Flight number (e.g. UA415)"),
    origin: Optional[str] = Query(None, description="Origin airport code (e.g. ORD)"),
    destination: Optional[str] = Query(None, description="Destination airport code (e.g. DEN)"),
    date: Optional[str] = Query(None, description="Flight date in YYYY-MM-DD format"),
    delay_status: Optional[str] = Query(None, description="Filter: DELAYED, ON_TIME, CANCELLED, LANDED"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: connection = Depends(get_db),
) -> FlightListResponse:
    """Search and filter flights stored in the FlightPulse database."""
    return search_flights(
        conn=conn,
        airline=airline,
        flight_number=flight_number,
        origin=origin,
        destination=destination,
        date=date,
        delay_status=delay_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{flight_id}", response_model=FlightDetailResponse)
def get_flight(
    flight_id: int,
    conn: connection = Depends(get_db),
) -> FlightDetailResponse:
    """Retrieve full details for a flight by its primary key ID."""
    flight = get_flight_by_id(conn, flight_id)
    if not flight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flight with ID {flight_id} was not found.",
        )
    return flight
