"""
Deterministic scoring and evaluation module for FlightPulse Intelligence Engine.
Calculates temporal relevance, geographic alignment, weather/event severity,
duration overlaps, and delay magnitude consistency.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Tuple

from pipeline.intelligence.evidence import DisruptionEvidence, WeatherEvidence


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


def calculate_temporal_proximity(
    target_time: datetime,
    event_time: datetime,
    max_window_minutes: float = 180.0,
) -> float:
    """
    Calculate temporal proximity score [0.0, 1.0] between a flight event and an external event.
    Events closer to target_time receive higher scores; events beyond max_window receive 0.0.
    """
    delta_sec = abs((target_time - event_time).total_seconds())
    delta_min = delta_sec / 60.0

    if delta_min > max_window_minutes:
        return 0.0
    if delta_min <= 30.0:
        return 1.0
    if delta_min <= 60.0:
        return 0.85
    if delta_min <= 120.0:
        return 0.55
    return max(0.0, 1.0 - (delta_min / max_window_minutes))


def calculate_duration_overlap(
    flight_scheduled_dep: datetime,
    flight_actual_dep: Optional[datetime],
    event_start: datetime,
    event_end: Optional[datetime],
) -> float:
    """
    Evaluate duration overlap [0.0, 1.0] between a flight's operational window and a disruption.
    Active ongoing disruptions during scheduled departure receive full score (1.0).
    Events occurring entirely after flight departure receive 0.0.
    """
    effective_dep = flight_actual_dep or flight_scheduled_dep

    # If disruption started after flight already departed, it cannot have caused the delay
    if event_start > effective_dep:
        return 0.0

    # Ongoing active disruption covering departure
    if event_start <= flight_scheduled_dep:
        if event_end is None or event_end >= flight_scheduled_dep:
            return 1.0
        # Disruption ended just prior to departure
        ended_prior_min = (flight_scheduled_dep - event_end).total_seconds() / 60.0
        if ended_prior_min <= 30.0:
            return 0.8
        if ended_prior_min <= 90.0:
            return 0.4
        return 0.0

    # Disruption started after scheduled departure but before actual departure (delayed while waiting)
    if flight_scheduled_dep < event_start <= effective_dep:
        return 0.85

    return 0.0


def evaluate_weather_severity(obs: WeatherEvidence) -> Tuple[float, List[str]]:
    """
    Analyze atmospheric observations to derive a deterministic severity score [0.0, 1.0]
    and concrete identified risk factors.
    """
    score = 0.0
    factors: List[str] = []
    code = (obs.condition_code or "").upper()

    # 1. Severe Phenomena
    if any(k in code for k in ("THUNDERSTORM", "TORNADO", "SQUALL", "HURRICANE")):
        score = max(score, 0.95)
        factors.append(f"Convective activity observed ({code})")
    elif any(k in code for k in ("HEAVY_SNOW", "BLIZZARD", "FREEZING_RAIN", "HAIL")):
        score = max(score, 0.90)
        factors.append(f"Severe winter precipitation ({code})")
    elif any(k in code for k in ("SNOW", "MODERATE_RAIN", "RAIN_SHOWERS")):
        score = max(score, 0.50)
        factors.append(f"Precipitation present ({code})")
    elif "FOG" in code:
        score = max(score, 0.60)
        factors.append(f"Surface fog conditions ({code})")

    # 2. Wind Conditions
    gusts = obs.wind_gust_knots or 0.0
    wind_spd = obs.wind_speed_knots or 0.0
    if gusts >= 40.0 or wind_spd >= 35.0:
        score = max(score, 0.90)
        factors.append(f"High crosswind/wind gusts ({max(gusts, wind_spd):.1f} knots)")
    elif gusts >= 28.0 or wind_spd >= 25.0:
        score = max(score, 0.65)
        factors.append(f"Gusty winds ({max(gusts, wind_spd):.1f} knots)")
    elif wind_spd >= 20.0:
        score = max(score, 0.35)
        factors.append(f"Moderate winds ({wind_spd:.1f} knots)")

    # 3. Visibility Restrictions
    vis = obs.visibility_miles
    if vis is not None:
        if vis <= 1.0:
            score = max(score, 0.90)
            factors.append(f"Critically restricted visibility ({vis:.2f} miles)")
        elif vis <= 3.0:
            score = max(score, 0.70)
            factors.append(f"Reduced visibility ({vis:.2f} miles)")
        elif vis <= 5.0:
            score = max(score, 0.40)
            factors.append(f"Marginal visibility ({vis:.2f} miles)")

    # Benign weather defaults to 0
    if not factors:
        score = 0.0

    return score, factors


def evaluate_disruption_severity(event: DisruptionEvidence) -> float:
    """Evaluate base severity [0.0, 1.0] from FAA / disruption event record."""
    sev = (event.severity or "").upper()
    etype = (event.event_type or "").upper()

    if sev == "CRITICAL" or etype == "GROUND_STOP":
        return 1.0
    if sev == "HIGH" or etype in ("AIRPORT_OUTAGE", "ATC_STRIKE"):
        return 0.85
    if sev == "MEDIUM" or etype == "SEVERE_WEATHER_ALERT":
        return 0.60
    return 0.30


def evaluate_delay_consistency(delay_minutes: int, signal_severity: float) -> float:
    """
    Evaluate whether the delay magnitude is consistent with the evidence strength.
    Flights with delay <= 15 minutes are on-time (consistency = 0.0).
    Large delays (>= 45m) with high signal severity receive full consistency (1.0).
    """
    if delay_minutes <= 15:
        # On-time flights receive no causal attribution
        return 0.0

    if delay_minutes >= 45:
        return 1.0 if signal_severity >= 0.6 else 0.7

    # 16-44 minute delay: moderate consistency
    if signal_severity >= 0.5:
        return 0.85
    return 0.50


def map_score_to_confidence(score: float) -> ConfidenceLevel:
    """Map numeric score in [0.0, 1.0] to standard qualitative confidence level."""
    if score >= 0.75:
        return ConfidenceLevel.HIGH
    if score >= 0.50:
        return ConfidenceLevel.MEDIUM
    if score >= 0.25:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.INSUFFICIENT
