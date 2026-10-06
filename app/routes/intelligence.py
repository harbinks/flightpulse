"""
Delay intelligence causal attribution routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extensions import connection

from app.database import get_db
from app.schemas.intelligence import DelayIntelligenceResponse
from app.services.intelligence_service import get_flight_intelligence

router = APIRouter(prefix="/flights", tags=["Intelligence"])


@router.get("/{flight_id}/intelligence", response_model=DelayIntelligenceResponse)
def get_intelligence_for_flight(
    flight_id: int,
    conn: connection = Depends(get_db),
) -> DelayIntelligenceResponse:
    """
    Execute deterministic delay intelligence analysis for a flight.
    Returns ranked candidate causes, confidence scores, supporting evidence, and primary attribution.
    """
    intelligence = get_flight_intelligence(conn, flight_id)
    if not intelligence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flight with ID {flight_id} was not found.",
        )
    return intelligence
