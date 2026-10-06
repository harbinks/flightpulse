"""
Comprehensive unit test suite for FlightPulse flight pipeline.
Validates timestamp parsing, delay calculation, callsign resolution,
in-batch deduplication, missing fields, unknown airports/airlines, and cancelled flights.
"""

from datetime import datetime, timezone
import pytest

from pipeline.transform.flights import (
    compute_delay_minutes,
    parse_callsign,
    parse_unix_timestamp,
    transform_flight_records,
)


# ============================================================================
# 1. Timestamp Conversion Tests
# ============================================================================

def test_parse_unix_timestamp_valid():
    # 2026-10-04 12:00:00 UTC = 1791115200
    ts = 1728043200  # 2024-10-04 12:00:00 UTC
    dt = parse_unix_timestamp(ts)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2024
    assert dt.month == 10
    assert dt.day == 4
    assert dt.hour == 12


def test_parse_unix_timestamp_invalid():
    # Negative epoch
    assert parse_unix_timestamp(-1000) is None
    # None or empty string
    assert parse_unix_timestamp(None) is None
    assert parse_unix_timestamp("") is None
    # Non-numeric string
    assert parse_unix_timestamp("invalid_epoch") is None
    # Absurd year (< 2000 or > 2100)
    assert parse_unix_timestamp(100) is None
    assert parse_unix_timestamp(999999999999) is None


# ============================================================================
# 2. Callsign Parsing Tests
# ============================================================================

def test_parse_callsign_valid():
    assert parse_callsign("DAL1042") == ("DAL", "DAL1042")
    assert parse_callsign("UAL415") == ("UAL", "UAL415")
    assert parse_callsign("AAL2401") == ("AAL", "AAL2401")
    assert parse_callsign("BAW178") == ("BAW", "BAW178")
    assert parse_callsign("DL1042") == ("DL", "DL1042")


def test_parse_callsign_invalid():
    assert parse_callsign("") == (None, None)
    assert parse_callsign(None) == (None, None)
    assert parse_callsign("12345") == (None, None)
    assert parse_callsign("JUSTTEXT") == (None, None)


# ============================================================================
# 3. Delay Calculation Tests
# ============================================================================

def test_compute_delay_minutes():
    sched = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
    
    # 45 minutes late
    actual_late = datetime(2026, 10, 4, 12, 45, 0, tzinfo=timezone.utc)
    assert compute_delay_minutes(sched, actual_late) == 45

    # 10 minutes early
    actual_early = datetime(2026, 10, 4, 11, 50, 0, tzinfo=timezone.utc)
    assert compute_delay_minutes(sched, actual_early) == -10

    # Exactly on-time
    assert compute_delay_minutes(sched, sched) == 0

    # Missing timestamps
    assert compute_delay_minutes(sched, None) == 0
    assert compute_delay_minutes(None, actual_late) == 0


# ============================================================================
# 4. Transformation & Validation Pipeline Tests
# ============================================================================

@pytest.fixture
def mock_lookups():
    """Mock reference dictionaries matching seeded airports and airlines."""
    airport_icao_map = {
        "KATL": 1,
        "KORD": 2,
        "KDFW": 3,
        "KDEN": 4,
        "KJFK": 5,
        "KLAX": 6,
        "KSFO": 7,
    }
    airport_iata_map = {
        "ATL": 1,
        "ORD": 2,
        "DFW": 3,
        "DEN": 4,
        "JFK": 5,
        "LAX": 6,
        "SFO": 7,
    }
    airline_icao_map = {
        "DAL": 1,
        "AAL": 2,
        "UAL": 3,
        "SWA": 4,
        "BAW": 5,
    }
    airline_iata_map = {
        "DL": 1,
        "AA": 2,
        "UA": 3,
        "WN": 4,
        "BA": 5,
    }
    return airport_icao_map, airport_iata_map, airline_icao_map, airline_iata_map


def test_transform_valid_flight(mock_lookups):
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [{
        "callsign": "DAL1042",
        "estDepartureAirport": "KATL",
        "estArrivalAirport": "KJFK",
        "scheduledDeparture": 1728043200,
        "scheduledArrival": 1728051300,
        "firstSeen": 1728043500,  # 5 min late
        "lastSeen": 1728051600,
        "icao24": "n12345",
    }]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
    )

    assert report.total_transformed == 1
    assert report.total_skipped == 0
    record = report.transformed[0]
    assert record.flight_number == "DAL1042"
    assert record.airline_id == 1
    assert record.origin_airport_id == 1
    assert record.destination_airport_id == 5
    assert record.status == "LANDED"
    assert record.departure_delay_minutes == 5


def test_transform_cancelled_flight(mock_lookups):
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [{
        "callsign": "UAL882",
        "estDepartureAirport": "KSFO",
        "estArrivalAirport": "KORD",
        "scheduledDeparture": 1728057600,
        "scheduledArrival": 1728079800,
        "isCancelled": True,
        "delayCategory": "WEATHER",
    }]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
    )

    assert report.total_transformed == 1
    record = report.transformed[0]
    assert record.status == "CANCELLED"
    assert record.actual_departure is None
    assert record.actual_arrival is None
    assert record.departure_delay_minutes == 0
    assert record.delay_category == "WEATHER"


def test_transform_in_batch_duplicates(mock_lookups):
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [
        {
            "callsign": "DAL1042",
            "estDepartureAirport": "KATL",
            "estArrivalAirport": "KJFK",
            "scheduledDeparture": 1728043200,
            "scheduledArrival": 1728051300,
        },
        {
            "callsign": "DAL1042",
            "estDepartureAirport": "KATL",
            "estArrivalAirport": "KJFK",
            "scheduledDeparture": 1728043200,
            "scheduledArrival": 1728051300,
        },
    ]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
    )

    assert report.total_transformed == 1
    assert report.duplicate_count == 1


def test_transform_missing_required_fields(mock_lookups):
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [
        # Missing callsign
        {"estDepartureAirport": "KATL", "estArrivalAirport": "KJFK", "scheduledDeparture": 1728043200},
        # Missing arrival airport
        {"callsign": "DAL1042", "estDepartureAirport": "KATL", "scheduledDeparture": 1728043200},
        # Identical origin and destination
        {"callsign": "DAL1042", "estDepartureAirport": "KATL", "estArrivalAirport": "KATL", "scheduledDeparture": 1728043200},
    ]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
    )

    assert report.total_transformed == 0
    assert report.total_skipped == 3
    reasons = [item["reason"] for item in report.skipped_records]
    assert "MISSING_CALLSIGN" in reasons
    assert "MISSING_AIRPORT_CODES" in reasons
    assert "IDENTICAL_ORIGIN_DESTINATION" in reasons


def test_transform_unknown_airport_and_airline(mock_lookups):
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [
        # Unknown airline
        {
            "callsign": "ZZZ999",
            "estDepartureAirport": "KATL",
            "estArrivalAirport": "KJFK",
            "scheduledDeparture": 1728043200,
        },
        # Unknown origin airport
        {
            "callsign": "DAL1042",
            "estDepartureAirport": "ZZZZ",
            "estArrivalAirport": "KJFK",
            "scheduledDeparture": 1728043200,
        },
    ]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
    )

    assert report.total_transformed == 0
    assert report.total_skipped == 2
    reasons = [item["reason"] for item in report.skipped_records]
    assert "UNKNOWN_AIRLINE" in reasons
    assert "UNKNOWN_ORIGIN_AIRPORT" in reasons


def test_transform_invalid_timestamp(mock_lookups):
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [{
        "callsign": "DAL1042",
        "estDepartureAirport": "KATL",
        "estArrivalAirport": "KJFK",
        "scheduledDeparture": -999999,
    }]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
    )

    assert report.total_transformed == 0
    assert report.total_skipped == 1
    assert report.skipped_records[0]["reason"] == "INVALID_SCHEDULED_DEPARTURE_TIMESTAMP"
