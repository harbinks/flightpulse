"""
Pydantic schemas for weather observation endpoints.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class WeatherObservationItem(BaseModel):
    """Individual atmospheric observation record."""
    id: int
    airport_id: int
    airport_code: str
    is_origin: bool
    observation_time: datetime
    temperature_c: Optional[float] = None
    dewpoint_c: Optional[float] = None
    wind_speed_knots: Optional[float] = None
    wind_gust_knots: Optional[float] = None
    wind_direction_deg: Optional[int] = None
    visibility_miles: Optional[float] = None
    altimeter_inhg: Optional[float] = None
    condition_code: str
    raw_metar: Optional[str] = None
    data_source: Optional[str] = None


class FlightWeatherResponse(BaseModel):
    """Weather context response for a flight at origin and destination."""
    flight_id: int
    flight_number: str
    origin_airport: str
    destination_airport: str
    origin_observations: List[WeatherObservationItem]
    destination_observations: List[WeatherObservationItem]
