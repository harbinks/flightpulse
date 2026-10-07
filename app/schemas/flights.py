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
    airline_name: Optional[str] = None
    airline_iata: Optional[str] = None
    origin_iata: Optional[str] = None
    origin_city: Optional[str] = None
    destination_iata: Optional[str] = None
    destination_city: Optional[str] = None
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
    data_source: Optional[str] = None


class FlightDetailResponse(BaseModel):
    """Full detail model for a single flight."""
    id: int
    flight_number: str
    airline_id: Optional[int] = None
    airline_name: Optional[str] = None
    airline_iata: Optional[str] = None
    origin_airport_id: Optional[int] = None
    origin_iata: Optional[str] = None
    origin_name: Optional[str] = None
    origin_city: Optional[str] = None
    origin_timezone: Optional[str] = None
    destination_airport_id: Optional[int] = None
    destination_iata: Optional[str] = None
    destination_name: Optional[str] = None
    destination_city: Optional[str] = None
    destination_timezone: Optional[str] = None
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
