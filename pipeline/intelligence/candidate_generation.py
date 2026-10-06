"""
Candidate cause generation and ranking module for FlightPulse Intelligence Engine.
Evaluates evidence across WEATHER, ATC, AIRPORT_DISRUPTION, SECURITY, and AIRLINE_OPERATIONAL,
producing deterministic, ranked causal candidates.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pipeline.intelligence.evidence import FlightEvidenceBundle
from pipeline.intelligence.scoring import (
    ConfidenceLevel,
    calculate_duration_overlap,
    calculate_temporal_proximity,
    evaluate_delay_consistency,
    evaluate_disruption_severity,
    evaluate_weather_severity,
    map_score_to_confidence,
)


@dataclass
class CandidateCause:
    """A single candidate explanation for a flight delay supported by evidence."""
    category: str  # 'WEATHER', 'ATC', 'AIRPORT_DISRUPTION', 'SECURITY', 'AIRLINE_OPERATIONAL', 'UNKNOWN'
    score: float   # 0.0 to 1.0
    confidence: ConfidenceLevel
    evidence: List[str] = field(default_factory=list)
    primary_signal: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "score": round(self.score, 2),
            "confidence": self.confidence.value,
            "primary_signal": self.primary_signal,
            "evidence": self.evidence,
        }


@dataclass
class DelayAnalysisResult:
    """Complete intelligence analysis result for a flight."""
    flight_id: int
    flight_number: str
    airline: str
    origin: str
    destination: str
    scheduled_departure: str
    actual_departure: Optional[str]
    departure_delay_minutes: int
    status: str
    reported_delay_category: Optional[str]
    candidates: List[CandidateCause] = field(default_factory=list)
    primary_candidate: str = "UNKNOWN / INSUFFICIENT_EVIDENCE"
    is_on_time: bool = False
    explanation_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flight_id": self.flight_id,
            "flight_number": self.flight_number,
            "airline": self.airline,
            "route": f"{self.origin} -> {self.destination}",
            "scheduled_departure": self.scheduled_departure,
            "actual_departure": self.actual_departure,
            "departure_delay_minutes": self.departure_delay_minutes,
            "status": self.status,
            "reported_delay_category": self.reported_delay_category,
            "is_on_time": self.is_on_time,
            "primary_candidate": self.primary_candidate,
            "explanation_summary": self.explanation_summary,
            "candidates": [c.to_dict() for c in self.candidates],
        }

    def format_display(self) -> str:
        """Render a formatted, human-readable intelligence report."""
        lines = [
            f"Flight: {self.flight_number} ({self.airline})",
            f"Route: {self.origin} -> {self.destination}",
            f"Scheduled Departure: {self.scheduled_departure}",
            f"Actual Departure:    {self.actual_departure or 'N/A'}",
            f"Delay:               {self.departure_delay_minutes} minutes ({self.status})",
            f"Reported Category:   {self.reported_delay_category or 'None specified'}",
            "",
            "Candidate Causes:",
        ]

        if not self.candidates or self.primary_candidate == "UNKNOWN / INSUFFICIENT_EVIDENCE":
            lines.append("  1. UNKNOWN / INSUFFICIENT_EVIDENCE")
            lines.append("     Score:      0.00")
            lines.append("     Confidence: INSUFFICIENT")
            lines.append("     Evidence:")
            lines.append("     - No external weather, ATC, or disruption events met relevance thresholds.")
        else:
            for idx, c in enumerate(self.candidates, 1):
                lines.append(f"  {idx}. {c.category}")
                lines.append(f"     Score:      {c.score:.2f}")
                lines.append(f"     Confidence: {c.confidence.value}")
                lines.append("     Evidence:")
                for ev in c.evidence:
                    lines.append(f"     - {ev}")
                lines.append("")

        lines.extend([
            "Final Attribution:",
            f"  PRIMARY CANDIDATE:   {self.primary_candidate}",
            f"  Summary:             {self.explanation_summary}",
        ])
        return "\n".join(lines)


def generate_candidates_for_flight(bundle: FlightEvidenceBundle) -> DelayAnalysisResult:
    """
    Apply deterministic causal reasoning to an evidence bundle to generate ranked candidates.
    """
    flight = bundle.flight
    delay_min = flight.departure_delay_minutes
    sched_dep = flight.scheduled_departure
    actual_dep = flight.actual_departure

    # 1. On-time handling (Delay <= 15 minutes per standard FAA criteria)
    if delay_min <= 15 and flight.status != "CANCELLED":
        return DelayAnalysisResult(
            flight_id=flight.flight_id,
            flight_number=flight.flight_number,
            airline=flight.airline_name,
            origin=flight.origin_iata,
            destination=flight.destination_iata,
            scheduled_departure=sched_dep.isoformat(),
            actual_departure=actual_dep.isoformat() if actual_dep else None,
            departure_delay_minutes=delay_min,
            status=flight.status,
            reported_delay_category=flight.delay_category,
            candidates=[],
            primary_candidate="ON_TIME / OPERATIONAL_TOLERANCE",
            is_on_time=True,
            explanation_summary=f"Flight operated within normal schedule tolerances (departure delay of {delay_min} min <= 15 min threshold). No disruption attribution required.",
        )

    candidates: List[CandidateCause] = []

    # -------------------------------------------------------------------------
    # 2. Evaluate WEATHER Candidate
    # -------------------------------------------------------------------------
    best_weather_score = 0.0
    weather_evidence_items: List[str] = []
    weather_signal_name = ""

    for obs in bundle.weather_observations:
        # Origin weather holds primary importance for departure delays
        if not obs.is_origin:
            continue

        sev_score, factors = evaluate_weather_severity(obs)
        if sev_score <= 0.0:
            continue

        temporal_score = calculate_temporal_proximity(sched_dep, obs.observation_time)
        if temporal_score <= 0.0:
            continue

        consistency_score = evaluate_delay_consistency(delay_min, sev_score)

        # Composite weather score
        wx_composite = (0.40 * sev_score) + (0.35 * temporal_score) + (0.25 * consistency_score)
        if wx_composite > best_weather_score:
            best_weather_score = wx_composite
            weather_signal_name = f"Adverse weather observed at {obs.airport_code} ({obs.condition_code})"
            weather_evidence_items = [
                f"Weather station at {obs.airport_code} reported {obs.condition_code} at {obs.observation_time.strftime('%H:%M UTC')}",
            ]
            for factor in factors:
                weather_evidence_items.append(factor)
            weather_evidence_items.append(
                f"Observation occurred {int(abs((sched_dep - obs.observation_time).total_seconds()) / 60)} minutes from scheduled departure"
            )

    if best_weather_score >= 0.35:
        candidates.append(CandidateCause(
            category="WEATHER",
            score=best_weather_score,
            confidence=map_score_to_confidence(best_weather_score),
            evidence=weather_evidence_items,
            primary_signal=weather_signal_name,
        ))

    # -------------------------------------------------------------------------
    # 3. Evaluate Disruption Events (ATC, Airport Outage, Strike, Security)
    # -------------------------------------------------------------------------
    for disp in bundle.disruptions:
        # Check geographic alignment
        is_origin = (disp.affected_airport_id == flight.origin_airport_id)
        is_dest = (disp.affected_airport_id == flight.destination_airport_id)
        is_airline_match = (disp.affected_airline_id == flight.airline_id)
        is_system_wide = (disp.affected_airport_id is None and disp.affected_airline_id is None)

        if not (is_origin or is_dest or is_airline_match or is_system_wide):
            # Unrelated event (e.g. JFK closure for an ORD->DEN flight) - strictly skip
            continue

        overlap_score = calculate_duration_overlap(sched_dep, actual_dep, disp.start_time, disp.end_time)
        if overlap_score <= 0.0:
            continue

        event_sev = evaluate_disruption_severity(disp)
        consistency = evaluate_delay_consistency(delay_min, event_sev)

        geo_weight = 1.0 if is_origin else (0.7 if is_airline_match else 0.5)
        composite_score = ((0.40 * event_sev) + (0.35 * overlap_score) + (0.25 * consistency)) * geo_weight

        if composite_score < 0.35:
            continue

        # Map to category
        category = "ATC"
        if disp.event_type == "GROUND_STOP" or disp.event_type == "ATC_STRIKE":
            category = "ATC"
        elif disp.event_type == "AIRPORT_OUTAGE":
            category = "AIRPORT_DISRUPTION"
        elif disp.event_type == "SECURITY_INCIDENT":
            category = "SECURITY"
        elif disp.event_type == "GENERAL_DISRUPTION" and is_airline_match:
            category = "AIRLINE_OPERATIONAL"
        elif disp.event_type == "SEVERE_WEATHER_ALERT":
            category = "WEATHER"

        ev_items = [
            f"{disp.title} (Severity: {disp.severity})",
            f"Event active from {disp.start_time.strftime('%H:%M UTC')} to {disp.end_time.strftime('%H:%M UTC') if disp.end_time else 'ongoing'}",
            f"Directly affected {'origin ' + flight.origin_iata if is_origin else ('airline ' + flight.airline_iata if is_airline_match else 'regional airspace')}",
        ]
        if disp.summary:
            ev_items.append(f"Detail: {disp.summary[:150]}")

        candidates.append(CandidateCause(
            category=category,
            score=composite_score,
            confidence=map_score_to_confidence(composite_score),
            evidence=ev_items,
            primary_signal=disp.title,
        ))

    # -------------------------------------------------------------------------
    # 4. Evaluate Flight Lifecycle Events (Audits, Gate changes, Turnaround)
    # -------------------------------------------------------------------------
    for fe in bundle.flight_events:
        meta = fe.metadata or {}
        fe_reason = str(meta.get("reason") or fe.description or "").upper()
        if "GROUND STOP" in fe_reason or "WEATHER" in fe_reason:
            # Lifecycle event confirms external restriction
            for c in candidates:
                if c.category in ("ATC", "WEATHER"):
                    c.evidence.append(f"Flight dispatch record confirmed: '{fe.description}' at {fe.event_time.strftime('%H:%M UTC')}")
                    c.score = min(1.0, c.score + 0.05)
                    c.confidence = map_score_to_confidence(c.score)

        elif flight.delay_category in ("CARRIER", "LATE_AIRCRAFT") and any(k in fe_reason for k in ("CREW", "TURNAROUND", "GATE", "MAINTENANCE")):
            candidates.append(CandidateCause(
                category="AIRLINE_OPERATIONAL",
                score=0.75,
                confidence=ConfidenceLevel.HIGH,
                evidence=[
                    f"Operational dispatch audit recorded: '{fe.description}'",
                    f"Source reported delay category: {flight.delay_category}",
                ],
                primary_signal="Airline operational dispatch delay",
            ))

    # Sort candidates by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)

    # -------------------------------------------------------------------------
    # 5. Resolve Primary Candidate & Interactions
    # -------------------------------------------------------------------------
    if not candidates or candidates[0].score < 0.40:
        primary = "UNKNOWN / INSUFFICIENT_EVIDENCE"
        summary = f"Departure delay of {delay_min} minutes was recorded, but available weather observations and disruption feeds provide insufficient evidence for causal attribution."
    else:
        top = candidates[0]
        # Check for multi-signal interaction (e.g. ATC Ground Stop triggered by Weather)
        categories = {c.category for c in candidates if c.score >= 0.70}
        if "ATC" in categories and "WEATHER" in categories:
            primary = "ATC / WEATHER INTERACTION"
            summary = (
                f"Flight delay of {delay_min} minutes strongly correlates with an Air Traffic Control restriction "
                f"(e.g. Ground Stop / Flow Management) compounded by severe convective weather conditions at {flight.origin_iata}."
            )
        else:
            primary = top.category
            summary = (
                f"Primary causal candidate identified as {top.category} (Confidence: {top.confidence.value}, Score: {top.score:.2f}) "
                f"based on {len(top.evidence)} supporting operational evidence signals."
            )

    return DelayAnalysisResult(
        flight_id=flight.flight_id,
        flight_number=flight.flight_number,
        airline=flight.airline_name,
        origin=flight.origin_iata,
        destination=flight.destination_iata,
        scheduled_departure=sched_dep.isoformat(),
        actual_departure=actual_dep.isoformat() if actual_dep else None,
        departure_delay_minutes=delay_min,
        status=flight.status,
        reported_delay_category=flight.delay_category,
        candidates=candidates,
        primary_candidate=primary,
        is_on_time=False,
        explanation_summary=summary,
    )
