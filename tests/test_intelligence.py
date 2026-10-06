"""
Comprehensive unit test suite for FlightPulse Flight Delay Intelligence Engine.
Tests deterministic causal attribution across weather, ATC, airport outages,
unrelated disruptions, multi-signal interactions, and insufficient evidence cases.
"""

from datetime import datetime, timedelta, timezone
import pytest

from pipeline.intelligence.candidate_generation import generate_candidates_for_flight
from pipeline.intelligence.evidence import (
    DisruptionEvidence,
    FlightDetail,
    FlightEventEvidence,
    FlightEvidenceBundle,
    WeatherEvidence,
)
from pipeline.intelligence.scoring import ConfidenceLevel


def create_base_flight(
    flight_id: int = 101,
    flight_number: str = "UA415",
    origin_iata: str = "ORD",
    destination_iata: str = "DEN",
    origin_id: int = 2,
    destination_id: int = 4,
    airline_id: int = 3,
    departure_delay_minutes: int = 105,
    scheduled_departure: datetime = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc),
    actual_departure: datetime = datetime(2026, 10, 4, 16, 15, tzinfo=timezone.utc),
    reported_delay_category: str = "WEATHER",
    status: str = "LANDED",
) -> FlightDetail:
    return FlightDetail(
        flight_id=flight_id,
        flight_number=flight_number,
        airline_id=airline_id,
        airline_name="United Airlines",
        airline_iata="UA",
        origin_airport_id=origin_id,
        origin_iata=origin_iata,
        origin_name="Chicago O'Hare",
        destination_airport_id=destination_id,
        destination_iata=destination_iata,
        destination_name="Denver International",
        flight_date=scheduled_departure.strftime("%Y-%m-%d"),
        scheduled_departure=scheduled_departure,
        actual_departure=actual_departure,
        scheduled_arrival=scheduled_departure + timedelta(hours=2),
        actual_arrival=actual_departure + timedelta(hours=2) if actual_departure else None,
        status=status,
        departure_delay_minutes=departure_delay_minutes,
        arrival_delay_minutes=departure_delay_minutes,
        delay_category=reported_delay_category,
        tail_number="N77014",
        aircraft_type="B772",
    )


# ============================================================================
# 1. On-Time Flight with No Disruption (Test 1)
# ============================================================================

def test_clear_weather_on_time_flight():
    flight = create_base_flight(
        flight_number="DL1042",
        departure_delay_minutes=3,
        scheduled_departure=datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc),
        actual_departure=datetime(2026, 10, 4, 12, 3, tzinfo=timezone.utc),
        reported_delay_category=None,
    )
    bundle = FlightEvidenceBundle(flight=flight)
    result = generate_candidates_for_flight(bundle)

    assert result.is_on_time is True
    assert result.primary_candidate == "ON_TIME / OPERATIONAL_TOLERANCE"
    assert len(result.candidates) == 0
    assert "normal schedule tolerances" in result.explanation_summary


# ============================================================================
# 2. Severe Weather Near Departure (Test 2)
# ============================================================================

def test_severe_weather_near_departure():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    flight = create_base_flight(departure_delay_minutes=60, scheduled_departure=sched)

    # Thunderstorm observation 20 minutes after scheduled departure
    wx = WeatherEvidence(
        airport_id=2,
        airport_code="ORD",
        observation_time=sched + timedelta(minutes=20),
        temperature_c=19.5,
        wind_speed_knots=28.0,
        wind_gust_knots=42.0,
        wind_direction_deg=290,
        visibility_miles=2.5,
        altimeter_inhg=29.74,
        condition_code="THUNDERSTORM",
        raw_metar="KORD +TSRA 42KT",
        is_origin=True,
    )

    bundle = FlightEvidenceBundle(flight=flight, weather_observations=[wx])
    result = generate_candidates_for_flight(bundle)

    assert result.is_on_time is False
    assert len(result.candidates) > 0
    wx_candidate = next((c for c in result.candidates if c.category == "WEATHER"), None)
    assert wx_candidate is not None
    assert wx_candidate.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
    assert any("Thunderstorm" in ev or "THUNDERSTORM" in ev for ev in wx_candidate.evidence)


# ============================================================================
# 3. Airport Ground Stop Overlapping Departure (Test 3)
# ============================================================================

def test_ground_stop_overlapping_departure():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    flight = create_base_flight(departure_delay_minutes=90, scheduled_departure=sched)

    # Active ground stop covering scheduled departure (14:15 to 16:00)
    disp = DisruptionEvidence(
        event_id=1,
        title="FAA Ground Stop: Chicago O'Hare",
        summary="Convective activity halts operations",
        source="FAA ATCSCC",
        url="https://nasstatus.faa.gov/gs-01",
        event_type="GROUND_STOP",
        severity="CRITICAL",
        affected_airport_id=2,
        affected_airport_code="ORD",
        affected_airline_id=None,
        affected_airline_code=None,
        start_time=sched - timedelta(minutes=15),
        end_time=sched + timedelta(hours=1, minutes=30),
    )

    bundle = FlightEvidenceBundle(flight=flight, disruptions=[disp])
    result = generate_candidates_for_flight(bundle)

    atc_candidate = next((c for c in result.candidates if c.category == "ATC"), None)
    assert atc_candidate is not None
    assert atc_candidate.confidence == ConfidenceLevel.HIGH
    assert atc_candidate.score >= 0.75
    assert "FAA Ground Stop" in atc_candidate.primary_signal


# ============================================================================
# 4. Disruption at Unrelated Airport (Test 4)
# ============================================================================

def test_unrelated_airport_disruption():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    flight = create_base_flight(origin_iata="ORD", destination_iata="DEN", origin_id=2, destination_id=4)

    # Runway closure at JFK (airport_id 5)
    disp = DisruptionEvidence(
        event_id=2,
        title="Airport Runway Closure: JFK",
        summary="Pavement repairs at New York",
        source="FAA NOTAM",
        url=None,
        event_type="AIRPORT_OUTAGE",
        severity="HIGH",
        affected_airport_id=5,  # JFK, not ORD or DEN
        affected_airport_code="JFK",
        affected_airline_id=None,
        affected_airline_code=None,
        start_time=sched - timedelta(minutes=30),
        end_time=sched + timedelta(hours=2),
    )

    bundle = FlightEvidenceBundle(flight=flight, disruptions=[disp])
    result = generate_candidates_for_flight(bundle)

    # The unrelated JFK disruption must be completely filtered out
    assert not any("JFK" in c.primary_signal for c in result.candidates)
    assert result.primary_candidate == "UNKNOWN / INSUFFICIENT_EVIDENCE"


# ============================================================================
# 5. Event Occurring After Flight Departure (Test 5)
# ============================================================================

def test_event_occurring_after_departure():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    actual = datetime(2026, 10, 4, 16, 0, tzinfo=timezone.utc)
    flight = create_base_flight(departure_delay_minutes=90, scheduled_departure=sched, actual_departure=actual)

    # Ground stop issued at 19:00 (3 hours after flight already departed)
    disp = DisruptionEvidence(
        event_id=3,
        title="FAA Ground Stop: ORD Late Evening",
        summary="Late storms",
        source="FAA",
        url=None,
        event_type="GROUND_STOP",
        severity="CRITICAL",
        affected_airport_id=2,
        affected_airport_code="ORD",
        affected_airline_id=None,
        affected_airline_code=None,
        start_time=sched + timedelta(hours=4, minutes=30),  # 19:00
        end_time=sched + timedelta(hours=6),
    )

    bundle = FlightEvidenceBundle(flight=flight, disruptions=[disp])
    result = generate_candidates_for_flight(bundle)

    # Event occurring after actual departure cannot be considered a cause
    assert result.primary_candidate == "UNKNOWN / INSUFFICIENT_EVIDENCE"


# ============================================================================
# 6. Weather Observation Far From Departure (Test 6)
# ============================================================================

def test_weather_observation_far_from_departure():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    flight = create_base_flight(departure_delay_minutes=60, scheduled_departure=sched)

    # Storm was 5 hours before scheduled departure, sky cleared long ago
    wx = WeatherEvidence(
        airport_id=2,
        airport_code="ORD",
        observation_time=sched - timedelta(hours=5),
        temperature_c=18.0,
        wind_speed_knots=10.0,
        wind_gust_knots=None,
        wind_direction_deg=180,
        visibility_miles=2.0,
        altimeter_inhg=29.90,
        condition_code="THUNDERSTORM",
        raw_metar=None,
        is_origin=True,
    )

    bundle = FlightEvidenceBundle(flight=flight, weather_observations=[wx])
    result = generate_candidates_for_flight(bundle)

    # Observation beyond max window receives 0.0 proximity
    assert not any(c.category == "WEATHER" for c in result.candidates)


# ============================================================================
# 7. Multiple Supporting Signals (Synergy) (Test 7 & 9)
# ============================================================================

def test_multiple_supporting_signals_atc_and_weather_interaction():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    flight = create_base_flight(departure_delay_minutes=105, scheduled_departure=sched)

    # Thunderstorm at origin
    wx = WeatherEvidence(
        airport_id=2,
        airport_code="ORD",
        observation_time=sched + timedelta(minutes=21),
        temperature_c=19.5,
        wind_speed_knots=28.0,
        wind_gust_knots=42.0,
        wind_direction_deg=290,
        visibility_miles=2.5,
        altimeter_inhg=29.74,
        condition_code="THUNDERSTORM",
        raw_metar="KORD TSRA",
        is_origin=True,
    )

    # FAA Ground Stop overlapping departure
    disp = DisruptionEvidence(
        event_id=1,
        title="FAA Ground Stop: Chicago O'Hare Convective Storms",
        summary="Severe weather line",
        source="FAA ATCSCC",
        url="https://nasstatus.faa.gov/gs-01",
        event_type="GROUND_STOP",
        severity="CRITICAL",
        affected_airport_id=2,
        affected_airport_code="ORD",
        affected_airline_id=None,
        affected_airline_code=None,
        start_time=sched - timedelta(minutes=15),
        end_time=sched + timedelta(hours=1, minutes=30),
    )

    # Flight event dispatch audit
    fe = FlightEventEvidence(
        event_id=10,
        event_type="DELAY_UPDATE",
        event_time=sched - timedelta(minutes=10),
        description="Departure delay announced due to FAA ORD ground stop",
        metadata={"initial_delay_minutes": 60, "reason": "FAA Ground Stop - Thunderstorms"},
    )

    bundle = FlightEvidenceBundle(flight=flight, weather_observations=[wx], disruptions=[disp], flight_events=[fe])
    result = generate_candidates_for_flight(bundle)

    # Verifies candidate ranking, multi-signal synergy, and large delay with strong evidence
    assert result.primary_candidate == "ATC / WEATHER INTERACTION"
    categories = [c.category for c in result.candidates]
    assert "ATC" in categories
    assert "WEATHER" in categories
    assert result.candidates[0].score >= 0.80


# ============================================================================
# 8. Small Delay with Weak Evidence (Test 8)
# ============================================================================

def test_small_delay_weak_evidence():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    # 18 minute delay (just past 15 min threshold) with light drizzle
    flight = create_base_flight(departure_delay_minutes=18, scheduled_departure=sched)

    wx = WeatherEvidence(
        airport_id=2,
        airport_code="ORD",
        observation_time=sched,
        temperature_c=15.0,
        wind_speed_knots=8.0,
        wind_gust_knots=None,
        wind_direction_deg=90,
        visibility_miles=9.0,
        altimeter_inhg=30.00,
        condition_code="LIGHT_DRIZZLE",
        raw_metar=None,
        is_origin=True,
    )

    bundle = FlightEvidenceBundle(flight=flight, weather_observations=[wx])
    result = generate_candidates_for_flight(bundle)

    # Minor drizzle with small delay should receive low or insufficient score
    if result.candidates:
        assert result.candidates[0].confidence in (ConfidenceLevel.LOW, ConfidenceLevel.INSUFFICIENT)
    else:
        assert result.primary_candidate == "UNKNOWN / INSUFFICIENT_EVIDENCE"


# ============================================================================
# 10. Insufficient Evidence / UNKNOWN (Test 10)
# ============================================================================

def test_large_delay_with_insufficient_evidence():
    sched = datetime(2026, 10, 4, 14, 30, tzinfo=timezone.utc)
    # 75 minute delay, but clear skies and zero external disruption events
    flight = create_base_flight(departure_delay_minutes=75, scheduled_departure=sched, reported_delay_category=None)

    wx = WeatherEvidence(
        airport_id=2,
        airport_code="ORD",
        observation_time=sched,
        temperature_c=22.0,
        wind_speed_knots=5.0,
        wind_gust_knots=None,
        wind_direction_deg=120,
        visibility_miles=10.0,
        altimeter_inhg=30.10,
        condition_code="CLEAR",
        raw_metar=None,
        is_origin=True,
    )

    bundle = FlightEvidenceBundle(flight=flight, weather_observations=[wx], disruptions=[])
    result = generate_candidates_for_flight(bundle)

    # The engine must NOT invent or force a causal explanation
    assert result.primary_candidate == "UNKNOWN / INSUFFICIENT_EVIDENCE"
    assert "insufficient evidence" in result.explanation_summary
