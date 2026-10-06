"""
Pydantic schemas for FlightPulse Grounded AI Analyst service.
Defines structured input contexts, model generation outputs, and safe fallback responses.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GroundedEvidenceContext(BaseModel):
    """
    Structured factual context gathered from database and deterministic intelligence engine.
    Passed to the grounded prompt builder without external unverified data.
    """
    flight_id: int
    flight_number: str
    airline: str
    route: str
    flight_date: str
    scheduled_departure: Optional[str] = None
    actual_departure: Optional[str] = None
    departure_delay_minutes: Optional[int] = None
    status: str
    reported_delay_category: Optional[str] = None
    
    # Authoritative deterministic findings
    deterministic_cause: str
    deterministic_confidence: str
    deterministic_score: float
    candidate_causes: List[Dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    
    # Contextual observational signals
    weather_observations: List[str] = Field(default_factory=list)
    faa_disruptions: List[str] = Field(default_factory=list)
    timeline_milestones: List[str] = Field(default_factory=list)


class AIAnalystOutput(BaseModel):
    """
    Structured response payload returned by the LLM or populated by deterministic fallback.
    """
    summary: str = Field(description="High-level 1-2 sentence executive explanation of the delay.")
    primary_cause: str = Field(description="Primary attributed cause matching the deterministic engine.")
    confidence: str = Field(description="Confidence level reflecting the deterministic engine (HIGH, MEDIUM, LOW, INSUFFICIENT).")
    explanation: str = Field(description="Detailed narrative explaining how the meteorological and operational facts correlate with the delay.")
    evidence_used: List[str] = Field(default_factory=list, description="Specific factual data points cited in the explanation.")
    limitations: List[str] = Field(default_factory=list, description="Known operational uncertainties, missing data, or uncorroborated carrier reports.")


class FlightAIAnalysisResponse(BaseModel):
    """
    Complete response returned by GET /flights/{flight_id}/ai-analysis endpoint.
    Maintains robustness with explicit status, structured explanation, and deterministic preservation.
    """
    status: str = Field(description="'success' when Ollama answers, 'unavailable' when offline/fallback, 'error' on malformed output.")
    flight_id: int
    flight_number: str
    route: str
    departure_delay_minutes: Optional[int] = None
    reported_delay_category: Optional[str] = None
    
    # Structured analytical narrative
    analysis: AIAnalystOutput
    
    # Audit & provenance metadata
    is_grounded: bool = Field(default=True, description="Always True; ensures narrative is derived solely from factual evidence.")
    model_used: Optional[str] = Field(default=None, description="Local Ollama model identifier used for inference.")
    execution_time_ms: Optional[float] = Field(default=None, description="Inference latency in milliseconds.")
    
    # Preserved deterministic source of truth
    deterministic_attribution: Dict[str, Any] = Field(
        default_factory=dict,
        description="Preserved raw deterministic engine output for independent inspection."
    )
