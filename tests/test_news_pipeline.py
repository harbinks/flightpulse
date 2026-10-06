"""
Unit test suite for FlightPulse news and disruption event ingestion pipeline.
Validates timestamp parsing, event type normalization, severity normalization,
airport/airline resolution, unknown location handling, duplicate deduplication,
and malformed record handling.
"""

from datetime import datetime, timezone
import pytest

from pipeline.transform.news import (
    normalize_event_type,
    normalize_severity,
    parse_event_timestamp,
    transform_news_records,
)


# ============================================================================
# 1. Timestamp Normalization Tests
# ============================================================================

def test_parse_event_timestamp_valid():
    # ISO-8601 UTC
    dt1 = parse_event_timestamp("2026-10-05T14:30:00Z")
    assert dt1 is not None
    assert dt1.tzinfo == timezone.utc
    assert dt1.year == 2026
    assert dt1.month == 10
    assert dt1.day == 5
    assert dt1.hour == 14
    assert dt1.minute == 30

    # FAA GMT format string: "Mon Oct 5 12:47:44 2026 GMT"
    dt2 = parse_event_timestamp("Mon Oct 5 12:47:44 2026 GMT")
    assert dt2 is not None
    assert dt2.tzinfo == timezone.utc
    assert dt2.year == 2026
    assert dt2.month == 10
    assert dt2.day == 5
    assert dt2.hour == 12
    assert dt2.minute == 47

    # Unix epoch
    dt3 = parse_event_timestamp(1728043200)
    assert dt3 is not None
    assert dt3.year == 2024


def test_parse_event_timestamp_invalid():
    assert parse_event_timestamp(None) is None
    assert parse_event_timestamp("") is None
    assert parse_event_timestamp("INVALID_DATE_STRING") is None
    assert parse_event_timestamp(-500) is None
    assert parse_event_timestamp(999999999999) is None


# ============================================================================
# 2. Event Type & Severity Normalization Tests
# ============================================================================

def test_normalize_event_type():
    assert normalize_event_type("Ground Stop", "FAA Ground Stop at ORD") == "GROUND_STOP"
    assert normalize_event_type("Airport Closure", "Runway 28R closed for repairs") == "AIRPORT_OUTAGE"
    assert normalize_event_type("Strike", "ATC controller walkout") == "ATC_STRIKE"
    assert normalize_event_type("Weather Alert", "Severe thunderstorm line crossing hub") == "SEVERE_WEATHER_ALERT"
    assert normalize_event_type("Security Incident", "TSA concourse evacuation") == "SECURITY_INCIDENT"
    assert normalize_event_type("Delay Program", "High traffic volume") == "GENERAL_DISRUPTION"


def test_normalize_severity():
    # Explicit severity values
    assert normalize_severity("CRITICAL") == "CRITICAL"
    assert normalize_severity("High") == "HIGH"
    assert normalize_severity("Moderate") == "MEDIUM"
    assert normalize_severity("Low") == "LOW"

    # Inferred from event type
    assert normalize_severity(None, event_type="GROUND_STOP") == "CRITICAL"
    assert normalize_severity(None, event_type="AIRPORT_OUTAGE") == "HIGH"
    assert normalize_severity(None, event_type="GENERAL_DISRUPTION") == "MEDIUM"


# ============================================================================
# 3. Transformation & Entity Resolution Tests
# ============================================================================

@pytest.fixture
def mock_lookups():
    airport_map = {
        "ORD": 2,
        "KORD": 2,
        "DFW": 3,
        "KDFW": 3,
        "LAX": 6,
        "KLAX": 6,
        "JFK": 5,
        "KJFK": 5,
    }
    airline_map = {
        "WN": 4,
        "SWA": 4,
        "AA": 2,
        "AAL": 2,
        "UA": 3,
        "UAL": 3,
    }
    return airport_map, airline_map


def test_transform_airport_only_event(mock_lookups):
    airport_map, airline_map = mock_lookups
    raw = [{
        "id": "EVT-ORD-01",
        "title": "FAA Ground Stop: Chicago O'Hare",
        "summary": "Thunderstorms halting departures",
        "source": "FAA ATCSCC",
        "url": "https://nasstatus.faa.gov/gs-01",
        "raw_type": "Ground Stop",
        "airport_code": "ORD",
        "airline_code": None,
        "start_time": "2026-10-05T14:00:00Z",
    }]

    report = transform_news_records(raw, airport_map, airline_map)
    assert report.total_transformed == 1
    assert report.total_skipped == 0
    rec = report.transformed[0]
    assert rec.airport_id == 2
    assert rec.airline_id is None  # Airport affected without specific airline
    assert rec.event_type == "GROUND_STOP"
    assert rec.severity == "CRITICAL"
    assert rec.url == "https://nasstatus.faa.gov/gs-01"


def test_transform_airline_only_event(mock_lookups):
    airport_map, airline_map = mock_lookups
    raw = [{
        "id": "EVT-WN-01",
        "title": "Southwest Airlines Fleet IT Recovery",
        "summary": "Dispatch software outage",
        "source": "Aviation Herald",
        "url": "https://avherald.com/news/wn-it",
        "raw_type": "System Outage",
        "airport_code": None,
        "airline_code": "WN",
        "start_time": "2026-10-05T13:00:00Z",
    }]

    report = transform_news_records(raw, airport_map, airline_map)
    assert report.total_transformed == 1
    rec = report.transformed[0]
    assert rec.airport_id is None  # Airline affected without specific airport
    assert rec.airline_id == 4
    assert rec.event_type == "AIRPORT_OUTAGE"


def test_transform_unknown_location_event(mock_lookups):
    airport_map, airline_map = mock_lookups
    raw = [{
        "id": "EVT-STRK-01",
        "title": "Regional Air Traffic Controller Walkout",
        "summary": "General industrial action across regional sector",
        "source": "Eurocontrol",
        "airport_code": "ZZZZ",  # Unknown airport code
        "airline_code": "XYZ",   # Unknown airline code
        "start_time": "2026-10-05T06:00:00Z",
    }]

    report = transform_news_records(raw, airport_map, airline_map)
    assert report.total_transformed == 1
    rec = report.transformed[0]
    # Relationships are NOT fabricated
    assert rec.airport_id is None
    assert rec.airline_id is None
    assert rec.event_type == "ATC_STRIKE"


def test_transform_duplicate_deduplication(mock_lookups):
    airport_map, airline_map = mock_lookups
    raw = [
        {
            "id": "EVT-DUP-01",
            "title": "Airport Closure: Runway 25L at LAX",
            "start_time": "2026-10-05T16:00:00Z",
            "airport_code": "LAX",
        },
        {
            "id": "EVT-DUP-01",
            "title": "Airport Closure: Runway 25L at LAX",
            "start_time": "2026-10-05T16:00:00Z",
            "airport_code": "LAX",
        },
    ]

    report = transform_news_records(raw, airport_map, airline_map)
    assert report.total_transformed == 1
    assert report.duplicate_count == 1


def test_transform_malformed_records(mock_lookups):
    airport_map, airline_map = mock_lookups
    raw = [
        # Missing title
        {"start_time": "2026-10-05T12:00:00Z", "airport_code": "ORD"},
        # Empty title string
        {"title": "   ", "start_time": "2026-10-05T12:00:00Z"},
        # Missing start time
        {"title": "Valid Title Missing Time"},
        # Invalid start time
        {"title": "Valid Title Invalid Time", "start_time": "UNPARSEABLE_TIME"},
        # Non-dict record
        "NOT_A_DICT_ENTRY",
    ]

    report = transform_news_records(raw, airport_map, airline_map)
    assert report.total_transformed == 0
    assert report.total_skipped == 5
    reasons = [sk["reason"] for sk in report.skipped_records]
    assert "MISSING_TITLE" in reasons
    assert "INVALID_OR_MISSING_START_TIME" in reasons
    assert "MALFORMED_RECORD_NOT_DICT" in reasons
