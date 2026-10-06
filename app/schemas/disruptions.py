"""
Pydantic schemas for operational disruptions and FAA advisories.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class DisruptionEventItem(BaseModel):
    """External operational disruption or FAA advisory record."""
    id: int
    title: str
    summary: Optional[str] = None
    source: str
    url: Optional[str] = None
    event_type: str
    severity: str
    affected_airport_code: Optional[str] = None
    affected_airline_code: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    data_source: Optional[str] = None


class FlightDisruptionsResponse(BaseModel):
    """Disruptions affecting a specific flight or its associated route/carrier."""
    flight_id: int
    flight_number: str
    disruptions: List[DisruptionEventItem]
