"""
Comprehensive unit and integration test suite for FlightPulse FastAPI application layer.
Tests all API routes, query filters, error handling, intelligence engine integration,
and chronological timeline ordering.
"""

from datetime import datetime
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ============================================================================
# 1. Health Check Endpoint
# ============================================================================

def test_health_endpoint():
    """Verify GET /health returns 200 OK and database connectivity."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "FlightPulse" in data["platform"]


# ============================================================================
# 2. Flight Search and Filter Endpoints
# ============================================================================

def test_list_flights_default():
    """Verify GET /flights returns paginated flight list."""
    response = client.get("/flights")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert data["total"] > 0
    assert len(data["flights"]) > 0
    flight = data["flights"][0]
    assert "flight_number" in flight
    assert "origin_iata" in flight
    assert "destination_iata" in flight


def test_list_flights_filter_by_airline():
    """Verify filtering flights by airline code."""
    response = client.get("/flights?airline=UA")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    for flight in data["flights"]:
        assert flight["airline_iata"] == "UA" or "United" in flight["airline_name"]


def test_list_flights_filter_by_flight_number():
    """Verify filtering flights by partial/exact flight number."""
    response = client.get("/flights?flight_number=415")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any("415" in f["flight_number"] for f in data["flights"])


def test_list_flights_filter_by_origin():
    """Verify filtering flights by origin airport IATA code."""
    response = client.get("/flights?origin=ORD")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    for flight in data["flights"]:
        assert flight["origin_iata"] == "ORD"


def test_list_flights_filter_by_delay_status():
    """Verify filtering flights by delay status (DELAYED vs ON_TIME)."""
    # Test DELAYED
    delayed_resp = client.get("/flights?delay_status=DELAYED")
    assert delayed_resp.status_code == 200
    delayed_data = delayed_resp.json()
    assert delayed_data["total"] > 0
    for f in delayed_data["flights"]:
        assert f["departure_delay_minutes"] > 15

    # Test ON_TIME
    ontime_resp = client.get("/flights?delay_status=ON_TIME")
    assert ontime_resp.status_code == 200
    ontime_data = ontime_resp.json()
    assert ontime_data["total"] > 0
    for f in ontime_data["flights"]:
        assert f["departure_delay_minutes"] <= 15


# ============================================================================
# 3. Get Flight by ID (Success)
# ============================================================================

def test_get_flight_by_id_success():
    """Verify GET /flights/{flight_id} retrieves detailed flight record."""
    response = client.get("/flights/2")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 2
    assert "415" in data["flight_number"]
    assert data["origin_iata"] == "ORD"
    assert data["destination_iata"] == "DEN"
    assert data["departure_delay_minutes"] == 105
    assert data["airline_name"] == "United Airlines"


# ============================================================================
# 4. Get Flight by ID (Not Found)
# ============================================================================

def test_get_flight_by_id_not_found():
    """Verify GET /flights/99999 returns 404 Not Found."""
    response = client.get("/flights/99999")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


# ============================================================================
# 5. Weather Endpoint for Flight
# ============================================================================

def test_get_flight_weather():
    """Verify GET /flights/{flight_id}/weather returns origin and destination weather."""
    response = client.get("/flights/2/weather")
    assert response.status_code == 200
    data = response.json()
    assert data["flight_id"] == 2
    assert data["origin_airport"] == "ORD"
    assert data["destination_airport"] == "DEN"
    # Flight 2 has weather observations near departure at ORD
    assert len(data["origin_observations"]) > 0
    obs = data["origin_observations"][0]
    assert "condition_code" in obs
    assert "wind_speed_knots" in obs
    assert "temperature_c" in obs


# ============================================================================
# 6. Disruption Notice Endpoint for Flight
# ============================================================================

def test_get_flight_disruptions():
    """Verify GET /flights/{flight_id}/disruptions returns FAA advisories."""
    response = client.get("/flights/2/disruptions")
    assert response.status_code == 200
    data = response.json()
    assert data["flight_id"] == 2
    assert "disruptions" in data
    assert len(data["disruptions"]) > 0
    # Flight 2 had ORD Ground Stop
    assert any(
        "GROUND_STOP" in d["event_type"] or "GROUND_DELAY" in d["event_type"]
        for d in data["disruptions"]
    )


# ============================================================================
# 7. Intelligence Attribution Endpoint
# ============================================================================

def test_get_flight_intelligence_attribution():
    """Verify GET /flights/{flight_id}/intelligence returns ranked candidates and evidence."""
    response = client.get("/flights/2/intelligence")
    assert response.status_code == 200
    data = response.json()

    # Verify flight metadata block
    assert data["flight"]["flight_number"] == "UA415"
    assert data["flight"]["route"] == "ORD -> DEN"
    assert data["delay"]["minutes"] == 105

    # Verify primary candidate
    primary = data["primary_candidate"]
    assert primary is not None
    assert primary["category"] in ("ATC / WEATHER INTERACTION", "ATC", "WEATHER")
    assert primary["confidence"] in ("HIGH", "MEDIUM")
    assert primary["score"] >= 0.65

    # Verify candidates list is ranked by score descending
    candidates = data["candidates"]
    assert len(candidates) >= 1
    scores = [c["score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)
    # Check evidence exists on top candidate
    assert len(candidates[0]["evidence"]) > 0


# ============================================================================
# 8. Intelligence Attribution on Uncontextualized / Low-Evidence Flight
# ============================================================================

def test_get_flight_intelligence_insufficient_evidence():
    """
    Verify GET /flights/{flight_id}/intelligence on flight without matching
    weather or disruption events returns UNKNOWN / INSUFFICIENT_EVIDENCE attribution.
    """
    # Flight 13 is UAL415 ingested from OpenSky without matching weather/FAA events
    response = client.get("/flights/13/intelligence")
    assert response.status_code == 200
    data = response.json()

    primary = data["primary_candidate"]
    assert primary is not None
    assert primary["category"] == "UNKNOWN / INSUFFICIENT_EVIDENCE"
    assert primary["confidence"] in ("LOW", "INSUFFICIENT")
    assert primary["score"] <= 0.30


# ============================================================================
# 9. Chronological Disruption Timeline Ordering
# ============================================================================

def test_get_flight_timeline_chronological_ordering():
    """
    Verify GET /flights/{flight_id}/timeline returns factual events
    in strictly non-decreasing chronological order (t[i] <= t[i+1]).
    """
    response = client.get("/flights/2/timeline")
    assert response.status_code == 200
    data = response.json()

    assert data["flight_id"] == 2
    assert data["total_events"] > 0
    timeline = data["timeline"]
    assert len(timeline) == data["total_events"]

    # Verify strict non-decreasing chronological order
    parsed_timestamps = [datetime.fromisoformat(item["time"]) for item in timeline]
    for i in range(len(parsed_timestamps) - 1):
        assert parsed_timestamps[i] <= parsed_timestamps[i + 1], (
            f"Timeline order violation at index {i}: "
            f"{timeline[i]['title']} ({timeline[i]['time']}) > "
            f"{timeline[i+1]['title']} ({timeline[i+1]['time']})"
        )

    # Verify presence of multiple factual categories
    categories = {item["category"] for item in timeline}
    assert "FLIGHT" in categories
    assert "WEATHER" in categories or "ATC" in categories or "AIRLINE" in categories


# ============================================================================
# 10. Error Handling & Input Validation
# ============================================================================

def test_api_error_handling_invalid_inputs():
    """Verify appropriate HTTP status codes on invalid parameters and non-existent IDs."""
    # Invalid flight ID format (non-integer string) returns 422 Unprocessable Entity
    invalid_id_resp = client.get("/flights/invalid_id")
    assert invalid_id_resp.status_code == 422

    # Non-existent flight on weather endpoint returns 404
    weather_404 = client.get("/flights/99999/weather")
    assert weather_404.status_code == 404
    assert "not found" in weather_404.json()["detail"].lower()

    # Non-existent flight on disruptions endpoint returns 404
    disrupt_404 = client.get("/flights/99999/disruptions")
    assert disrupt_404.status_code == 404
    assert "not found" in disrupt_404.json()["detail"].lower()

    # Non-existent flight on intelligence endpoint returns 404
    intel_404 = client.get("/flights/99999/intelligence")
    assert intel_404.status_code == 404
    assert "not found" in intel_404.json()["detail"].lower()

    # Non-existent flight on timeline endpoint returns 404
    timeline_404 = client.get("/flights/99999/timeline")
    assert timeline_404.status_code == 404
    assert "not found" in timeline_404.json()["detail"].lower()


# ============================================================================
# 11. Mode Provenance and DEMO/LIVE Isolation (Phase 10.2)
# ============================================================================

def test_list_flights_default_is_demo():
    """Verify default GET /flights only returns DEMO/FIXTURE records."""
    response = client.get("/flights")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    for flight in data["flights"]:
        assert flight.get("data_source") in ("DEMO", "FIXTURE", "FIXTURE_REPLAY", "FLIGHTAWARE")


def test_list_flights_explicit_demo_mode():
    """Verify GET /flights?mode=demo explicitly filters to DEMO records."""
    response = client.get("/flights?mode=demo")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    for flight in data["flights"]:
        assert flight.get("data_source") != "OPENSKY_LIVE"


def test_list_flights_live_mode_excludes_demo():
    """Verify GET /flights?mode=live excludes all DEMO/FIXTURE records."""
    response = client.get("/flights?mode=live")
    assert response.status_code == 200
    data = response.json()
    for flight in data["flights"]:
        assert flight.get("data_source") == "OPENSKY_LIVE"
        assert flight.get("data_source") not in ("DEMO", "FIXTURE", "FIXTURE_REPLAY", "FLIGHTAWARE")

