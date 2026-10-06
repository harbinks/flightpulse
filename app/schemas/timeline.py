"""
Pydantic schemas for chronological flight disruption timeline.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class TimelineEventItem(BaseModel):
    """A single factual event in the flight's chronological disruption timeline."""
    time: datetime
    event_type: str
    category: str  # 'FLIGHT', 'WEATHER', 'ATC', 'AIRPORT', 'AIRLINE'
    title: str
    detail: Optional[str] = None
    severity: Optional[str] = None
    source: Optional[str] = None


class FlightTimelineResponse(BaseModel):
    """Chronological event progression for a flight from existing database records."""
    flight_id: int
    flight_number: str
    route: str
    total_events: int
    timeline: List[TimelineEventItem]
