"""
Pydantic schemas for flight records and search endpoints.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class FlightSummary(BaseModel):
    """Lightweight flight summary for list views and search results."""
    id: int
    flight_number: str
    airline_name: str
    airline_iata: str
    origin_iata: str
    origin_city: str
    destination_iata: str
    destination_city: str
    flight_date: str
    scheduled_departure: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    scheduled_arrival: Optional[datetime] = None
    actual_arrival: Optional[datetime] = None
    status: str
    departure_delay_minutes: Optional[int] = None
    arrival_delay_minutes: Optional[int] = None
    delay_category: Optional[str] = None
    aircraft_type: Optional[str] = None


class FlightDetailResponse(BaseModel):
    """Full detail model for a single flight."""
    id: int
    flight_number: str
    airline_id: int
    airline_name: str
    airline_iata: str
    origin_airport_id: int
    origin_iata: str
    origin_name: str
    origin_city: str
    origin_timezone: str
    destination_airport_id: int
    destination_iata: str
    destination_name: str
    destination_city: str
    destination_timezone: str
    flight_date: str
    scheduled_departure: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    scheduled_arrival: Optional[datetime] = None
    actual_arrival: Optional[datetime] = None
    status: str
    departure_delay_minutes: Optional[int] = None
    arrival_delay_minutes: Optional[int] = None
    delay_category: Optional[str] = None
    tail_number: Optional[str] = None
    aircraft_type: Optional[str] = None
    distance_miles: Optional[float] = None
    data_source: Optional[str] = None


class FlightListResponse(BaseModel):
    """Response wrapper for flight search listings."""
    total: int
    flights: List[FlightSummary]
