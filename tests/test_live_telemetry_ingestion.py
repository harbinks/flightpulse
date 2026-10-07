"""
Tests for Phase 10.6: OpenSky Live Telemetry Ingestion Fix.
Verifies that real ADS-B telemetry observations with unseeded airlines,
missing/unseeded destinations, and unknown schedules are accepted with honest NULL semantics,
without fabricating commercial delays or corrupting DEMO records.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from pipeline.transform.flights import transform_flight_records
from pipeline.intelligence.analyzer import analyze_flight_delay
from pipeline.intelligence.evidence import FlightEvidenceBundle, FlightDetail
from pipeline.intelligence.candidate_generation import generate_candidates_for_flight


@pytest.fixture
def mock_lookups():
    airport_icao_map = {
        "KATL": 1,
        "KORD": 2,
        "KDEN": 3,
        "KJFK": 4,
    }
    airport_iata_map = {
        "ATL": 1,
        "ORD": 2,
        "DEN": 3,
        "JFK": 4,
    }
    airline_icao_map = {
        "DAL": 1,
        "AAL": 2,
        "UAL": 3,
    }
    airline_iata_map = {
        "DL": 1,
        "AA": 2,
        "UA": 3,
    }
    return airport_icao_map, airport_iata_map, airline_icao_map, airline_iata_map


def test_telemetry_unknown_airline_and_missing_destination(mock_lookups):
    """
    Test A, B, D, E, F, G, H, I, J:
    - Unknown airline (SKW) does NOT reject valid telemetry
    - Missing destination (None) does NOT reject valid telemetry
    - airline_id = None
    - destination_airport_id = None
    - scheduled_departure = None
    - scheduled_arrival = None
    - departure_delay_minutes = None
    - arrival_delay_minutes = None
    - delay_category = None
    """
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [{
        "callsign": "SKW5593 ",
        "icao24": "a1234b",
        "estDepartureAirport": "KORD",
        "estArrivalAirport": None,
        "firstSeen": 1728043200,
        "lastSeen": 1728046800,
    }]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
        data_source="OPENSKY_LIVE",
    )

    assert report.total_transformed == 1
    assert report.total_skipped == 0
    t = report.transformed[0]

    assert t.flight_number == "SKW5593"
    assert t.tail_number == "a1234b"
    assert t.airline_id is None
    assert t.origin_airport_id == 2  # KORD
    assert t.destination_airport_id is None
    assert t.scheduled_departure is None
    assert t.scheduled_arrival is None
    assert t.departure_delay_minutes is None
    assert t.arrival_delay_minutes is None
    assert t.delay_category is None
    assert t.status == "LANDED"
    assert t.data_source == "OPENSKY_LIVE"


def test_telemetry_unseeded_destination_airport(mock_lookups):
    """
    Test C:
    - Unseeded destination airport (KEWR) does not cause rejection or fabricate airport records.
    - destination_airport_id is None.
    """
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [{
        "callsign": "ENY3634 ",
        "icao24": "a5678c",
        "estDepartureAirport": "KORD",
        "estArrivalAirport": "KEWR",
        "firstSeen": 1728043200,
        "lastSeen": None,
    }]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
        data_source="OPENSKY_LIVE",
    )

    assert report.total_transformed == 1
    t = report.transformed[0]
    assert t.destination_airport_id is None
    assert t.origin_airport_id == 2  # KORD
    assert t.status == "EN_ROUTE"


def test_telemetry_missing_both_callsign_and_icao24_rejected(mock_lookups):
    """
    Test K:
    - Invalid telemetry missing both callsign and icao24 is rejected.
    """
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [{
        "callsign": None,
        "icao24": None,
        "estDepartureAirport": "KORD",
        "firstSeen": 1728043200,
    }]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
        data_source="OPENSKY_LIVE",
    )

    assert report.total_transformed == 0
    assert report.total_skipped == 1
    assert report.skipped_records[0]["reason"] == "MISSING_IDENTIFIER"


def test_telemetry_inbatch_deduplication(mock_lookups):
    """
    Test L:
    - Duplicate telemetry records with the same aircraft identity and observation timestamp
      are deduplicated within the batch.
    """
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [
        {
            "callsign": "SKW5593",
            "icao24": "a1234b",
            "estDepartureAirport": "KORD",
            "firstSeen": 1728043200,
        },
        {
            "callsign": "SKW5593",
            "icao24": "a1234b",
            "estDepartureAirport": "KORD",
            "firstSeen": 1728043200,
        },
    ]

    report = transform_flight_records(
        raw_records=raw,
        airport_icao_map=airport_icao,
        airport_iata_map=airport_iata,
        airline_icao_map=airline_icao,
        airline_iata_map=airline_iata,
        data_source="OPENSKY_LIVE",
    )

    assert report.total_transformed == 1
    assert report.duplicate_count == 1


def test_telemetry_deterministic_intelligence_insufficient_evidence():
    """
    Test N:
    - Telemetry-only records without scheduled departure or delay minutes
      return INSUFFICIENT_EVIDENCE / LIVE_TELEMETRY_ONLY.
    """
    now = datetime.now(timezone.utc)
    detail = FlightDetail(
        flight_id=999,
        flight_number="SKW5593",
        airline_id=None,
        airline_name=None,
        airline_iata=None,
        origin_airport_id=2,
        origin_iata="ORD",
        origin_name="Chicago O'Hare",
        destination_airport_id=None,
        destination_iata=None,
        destination_name=None,
        flight_date="2026-10-07",
        scheduled_departure=None,
        actual_departure=now,
        scheduled_arrival=None,
        actual_arrival=None,
        status="EN_ROUTE",
        departure_delay_minutes=None,
        arrival_delay_minutes=None,
        delay_category=None,
        tail_number="a1234b",
        aircraft_type=None,
    )

    bundle = FlightEvidenceBundle(flight=detail)
    res = generate_candidates_for_flight(bundle)

    assert "INSUFFICIENT_EVIDENCE" in res.primary_candidate or "LIVE_TELEMETRY_ONLY" in res.primary_candidate
    assert len(res.candidates) == 0
    assert res.departure_delay_minutes is None
    assert res.scheduled_departure is None
