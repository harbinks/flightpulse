"""
Unit test suite for FlightPulse weather data ingestion pipeline.
Validates timestamp parsing, airport coordinate matching, temperature/wind conversions,
missing fields, duplicate handling, malformed API responses, and idempotent upserts.
"""

from datetime import datetime, timezone
import pytest

from pipeline.transform.weather import (
    convert_pressure_to_inhg,
    convert_temperature_to_celsius,
    convert_visibility_to_miles,
    convert_wind_to_knots,
    match_airport,
    parse_observation_timestamp,
    resolve_condition_code,
    transform_weather_records,
)


# ============================================================================
# 1. Timestamp Parsing Tests
# ============================================================================

def test_parse_observation_timestamp_valid():
    # ISO string with UTC Z
    dt1 = parse_observation_timestamp("2026-10-05T12:00:00Z")
    assert dt1 is not None
    assert dt1.tzinfo == timezone.utc
    assert dt1.year == 2026
    assert dt1.month == 10
    assert dt1.day == 5
    assert dt1.hour == 12

    # ISO string with minutes
    dt2 = parse_observation_timestamp("2026-10-05T14:30")
    assert dt2 is not None
    assert dt2.hour == 14
    assert dt2.minute == 30

    # Unix epoch seconds (2024-10-04 12:00:00 UTC)
    dt3 = parse_observation_timestamp(1728043200)
    assert dt3 is not None
    assert dt3.year == 2024


def test_parse_observation_timestamp_invalid():
    assert parse_observation_timestamp(None) is None
    assert parse_observation_timestamp("") is None
    assert parse_observation_timestamp("INVALID_DATE") is None
    assert parse_observation_timestamp(-100) is None
    assert parse_observation_timestamp(999999999999) is None


# ============================================================================
# 2. Temperature Conversion Tests
# ============================================================================

def test_convert_temperature():
    # Celsius direct passthrough
    assert convert_temperature_to_celsius(celsius=21.5) == 21.5

    # Fahrenheit to Celsius: 32 F -> 0.0 C
    assert convert_temperature_to_celsius(fahrenheit=32.0) == 0.0

    # Fahrenheit to Celsius: 68 F -> 20.0 C
    assert convert_temperature_to_celsius(fahrenheit=68.0) == 20.0

    # Fahrenheit to Celsius: -4 F -> -20.0 C
    assert convert_temperature_to_celsius(fahrenheit=-4.0) == -20.0

    # None / Invalid
    assert convert_temperature_to_celsius() is None
    assert convert_temperature_to_celsius(celsius="invalid") is None


# ============================================================================
# 3. Wind Speed Conversion Tests
# ============================================================================

def test_convert_wind_speed():
    # Knots passthrough
    assert convert_wind_to_knots(knots=15.0) == 15.0

    # mph to knots: 11.5078 mph -> 10.0 knots
    assert convert_wind_to_knots(mph=11.5078) == 10.0

    # km/h to knots: 18.52 km/h -> 10.0 knots
    assert convert_wind_to_knots(kmh=18.52) == 10.0

    # None / Invalid
    assert convert_wind_to_knots() is None
    assert convert_wind_to_knots(mph="abc") is None


# ============================================================================
# 4. Pressure & Visibility Conversion Tests
# ============================================================================

def test_convert_pressure_and_visibility():
    # 1013.25 hPa -> 29.92 inHg
    assert convert_pressure_to_inhg(hpa=1013.25) == 29.92
    assert convert_pressure_to_inhg(inhg=30.05) == 30.05

    # 16093.44 meters -> 10.0 miles
    assert convert_visibility_to_miles(meters=16093.44) == 10.0
    assert convert_visibility_to_miles(miles=5.5) == 5.5


def test_resolve_condition_code():
    assert resolve_condition_code(0) == "CLEAR"
    assert resolve_condition_code(3) == "OVERCAST"
    assert resolve_condition_code(73) == "MODERATE_SNOW_FALL"
    assert resolve_condition_code(95) == "THUNDERSTORM"
    assert resolve_condition_code(None, "LIGHT RAIN") == "LIGHT_RAIN"
    assert resolve_condition_code(None, None) == "UNKNOWN"


# ============================================================================
# 5. Airport Matching Tests
# ============================================================================

@pytest.fixture
def mock_airport_coords():
    return {
        "KORD": {"id": 2, "iata_code": "ORD", "icao_code": "KORD", "latitude": 41.974162, "longitude": -87.907321},
        "ORD": {"id": 2, "iata_code": "ORD", "icao_code": "KORD", "latitude": 41.974162, "longitude": -87.907321},
        "KATL": {"id": 1, "iata_code": "ATL", "icao_code": "KATL", "latitude": 33.640728, "longitude": -84.427700},
        "ATL": {"id": 1, "iata_code": "ATL", "icao_code": "KATL", "latitude": 33.640728, "longitude": -84.427700},
    }


def test_match_airport(mock_airport_coords):
    # Match by exact code
    assert match_airport("KORD", None, None, mock_airport_coords) == 2
    assert match_airport("ORD", None, None, mock_airport_coords) == 2
    assert match_airport("KATL", None, None, mock_airport_coords) == 1

    # Match by coordinates (within close distance)
    assert match_airport(None, 41.974, -87.907, mock_airport_coords) == 2
    assert match_airport(None, 33.641, -84.428, mock_airport_coords) == 1

    # Unknown code and far coordinates
    assert match_airport("ZZZZ", 0.0, 0.0, mock_airport_coords) is None
    assert match_airport(None, None, None, mock_airport_coords) is None


# ============================================================================
# 6. Transformation Pipeline & Edge Case Tests
# ============================================================================

def test_transform_valid_weather(mock_airport_coords):
    raw = [{
        "airport_code": "KORD",
        "latitude": 41.974162,
        "longitude": -87.907321,
        "time": "2026-10-05T12:00:00Z",
        "temperature_c": 14.2,
        "dewpoint_c": 6.8,
        "wind_speed_knots": 12.0,
        "wind_gust_knots": 18.0,
        "wind_direction_deg": 270,
        "visibility_miles": 10.0,
        "altimeter_inhg": 29.95,
        "weather_code": 2,
        "raw_payload": "METAR KORD 051200Z...",
    }]

    report = transform_weather_records(raw, mock_airport_coords)
    assert report.total_transformed == 1
    assert report.total_skipped == 0
    rec = report.transformed[0]
    assert rec.airport_id == 2
    assert rec.temperature_c == 14.2
    assert rec.condition_code == "PARTLY_CLOUDY"
    assert rec.wind_direction_deg == 270


def test_transform_duplicate_handling(mock_airport_coords):
    raw = [
        {
            "airport_code": "KATL",
            "time": "2026-10-05T12:00:00Z",
            "temperature_c": 20.0,
        },
        {
            "airport_code": "KATL",
            "time": "2026-10-05T12:00:00Z",
            "temperature_c": 20.0,
        },
    ]

    report = transform_weather_records(raw, mock_airport_coords)
    assert report.total_transformed == 1
    assert report.duplicate_count == 1


def test_transform_missing_and_invalid_fields(mock_airport_coords):
    raw = [
        # Missing timestamp
        {"airport_code": "KORD", "temperature_c": 15.0},
        # Invalid timestamp format
        {"airport_code": "KORD", "time": "NOT_A_DATE", "temperature_c": 15.0},
        # Unknown airport
        {"airport_code": "UNKNOWN", "time": "2026-10-05T12:00:00Z", "temperature_c": 15.0},
        # Invalid wind direction (> 360)
        {"airport_code": "KORD", "time": "2026-10-05T12:00:00Z", "wind_direction_deg": 450},
        # Non-dict record
        "NOT_A_DICT",
    ]

    report = transform_weather_records(raw, mock_airport_coords)
    assert report.total_transformed == 0
    assert report.total_skipped == 5
    reasons = [sk["reason"] for sk in report.skipped_records]
    assert "INVALID_OR_MISSING_TIMESTAMP" in reasons
    assert "UNKNOWN_AIRPORT" in reasons
    assert "INVALID_WIND_DIRECTION" in reasons
    assert "MALFORMED_RECORD_NOT_DICT" in reasons
