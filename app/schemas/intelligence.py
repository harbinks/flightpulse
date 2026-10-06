"""
Pydantic schemas for the deterministic flight delay intelligence engine response.
Maintains strict separation between reported reason, inferred candidate causes, evidence, and confidence.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class CandidateCauseItem(BaseModel):
    """Ranked candidate explanation for flight delay."""
    category: str
    score: float
    confidence: str
    primary_signal: str
    evidence: List[str]


class DelayMetadata(BaseModel):
    """Delay statistics and upstream reported classifications."""
    minutes: int
    arrival_delay_minutes: int
    reported_category: Optional[str] = None
    status: str
    is_on_time: bool


class PrimaryAttribution(BaseModel):
    """Primary causal attribution decided by the intelligence engine."""
    category: str
    score: float
    confidence: str


class DelayIntelligenceResponse(BaseModel):
    """Full causal attribution response for a flight."""
    flight: Dict[str, Any]
    delay: DelayMetadata
    primary_candidate: PrimaryAttribution
    candidates: List[CandidateCauseItem]
    explanation_summary: str
