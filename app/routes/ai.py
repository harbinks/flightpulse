"""
Grounded AI Analyst API routes.
Exposes evidence-backed natural language flight delay explanations powered by local Ollama LLM.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extensions import connection

from app.database import get_db
from app.schemas.ai import FlightAIAnalysisResponse
from app.services.ai_analyst import analyze_flight_with_ai

router = APIRouter(prefix="/flights", tags=["AI Analyst"])


@router.get("/{flight_id}/ai-analysis", response_model=FlightAIAnalysisResponse)
def get_ai_delay_analysis(
    flight_id: int,
    conn: connection = Depends(get_db),
) -> FlightAIAnalysisResponse:
    """
    Generate an evidence-grounded natural language delay analysis for a flight.
    
    Architecture:
    - Gathers verified flight facts, METAR records, FAA notices, and dispatch events.
    - Preserves the deterministic intelligence engine as the single source of truth.
    - Constrains local Ollama LLM to synthesize narrative explanations strictly from evidence.
    - Automatically falls back to deterministic attribution if Ollama is offline or times out.
    """
    result = analyze_flight_with_ai(conn=conn, flight_id=flight_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Flight with ID {flight_id} was not found.",
        )
    return result
