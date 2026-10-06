"""
Weather observation routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extensions import connection

from app.database import get_db
from app.schemas.weather import FlightWeatherResponse
from app.services.flight_service import get_flight_weather

router = APIRouter(prefix="/flights", tags=["Weather"])


@router.get("/{flight_id}/weather", response_model=FlightWeatherResponse)
def get_weather_for_flight(
    flight_id: int,
    conn: connection = Depends(get_db),
) -> FlightWeatherResponse:
    """Retrieve weather observations near departure and arrival for a flight."""
    weather = get_flight_weather(conn, flight_id)
    if not weather:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flight with ID {flight_id} was not found.",
        )
    return weather
