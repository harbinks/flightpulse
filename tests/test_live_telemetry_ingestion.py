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


def test_telemetry_missing_callsign_uses_icao24(mock_lookups):
    """
    Test 9:
    - Valid telemetry missing callsign but having valid icao24 uses icao24 as identifier.
    """
    airport_icao, airport_iata, airline_icao, airline_iata = mock_lookups
    raw = [{
        "callsign": None,
        "icao24": "a9b8c7",
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
    assert t.flight_number == "A9B8C7"
    assert t.tail_number == "a9b8c7"
    assert t.airline_id is None


def test_opensky_http_200_extraction(monkeypatch):
    """
    Test 1:
    - OpenSky HTTP 200 returns parsed list of raw flight records.
    """
    from pipeline.extract.flights import extract_opensky_flights

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"icao24": "abc123", "callsign": "UAL100", "firstSeen": 1728040000}
    ]

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp
    monkeypatch.setattr("requests.Session", lambda: mock_session)

    records = extract_opensky_flights(
        airport_icao="KORD",
        begin_timestamp=1728030000,
        end_timestamp=1728040000,
    )
    assert len(records) == 1
    assert records[0]["callsign"] == "UAL100"


def test_opensky_http_200_empty_response(monkeypatch):
    """
    Test 5:
    - OpenSky HTTP 200 with empty list returns empty list without error.
    """
    from pipeline.extract.flights import extract_opensky_flights

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp
    monkeypatch.setattr("requests.Session", lambda: mock_session)

    records = extract_opensky_flights(
        airport_icao="KORD",
        begin_timestamp=1728030000,
        end_timestamp=1728040000,
    )
    assert records == []


def test_opensky_http_429_large_retry_header_raises_rate_limit(monkeypatch):
    """
    Test 2:
    - HTTP 429 with large Retry-After or X-Rate-Limit header raises OpenSkyRateLimitError
      without stalling indefinitely.
    """
    from pipeline.extract.flights import extract_opensky_flights, OpenSkyRateLimitError

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"X-Rate-Limit-Retry-After-Seconds": "82000"}

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp
    monkeypatch.setattr("requests.Session", lambda: mock_session)

    with pytest.raises(OpenSkyRateLimitError) as exc_info:
        extract_opensky_flights(
            airport_icao="KORD",
            begin_timestamp=1728030000,
            end_timestamp=1728040000,
            max_backoff_seconds=5.0,
        )

    assert "rate limit" in str(exc_info.value).lower()
    assert exc_info.value.retry_after_seconds == 82000.0


def test_opensky_http_429_retry_budget_exhausted(monkeypatch):
    """
    Test 3 & 4:
    - HTTP 429 without Retry-After exhausts bounded retry attempts and raises OpenSkyRateLimitError.
    """
    from pipeline.extract.flights import extract_opensky_flights, OpenSkyRateLimitError

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {}

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp
    monkeypatch.setattr("requests.Session", lambda: mock_session)
    monkeypatch.setattr("time.sleep", lambda s: None)

    with pytest.raises(OpenSkyRateLimitError):
        extract_opensky_flights(
            airport_icao="KORD",
            begin_timestamp=1728030000,
            end_timestamp=1728040000,
            max_retries=2,
            backoff_factor=1.0,
        )

    assert mock_session.get.call_count == 2


def test_orchestrator_handles_rate_limited_flights_partial_sync(monkeypatch):
    """
    Test 8, 14, 15:
    - When OpenSky raises OpenSkyRateLimitError, flights branch logs RATE_LIMITED
      and overall orchestration status is PARTIAL if weather/FAA succeed.
    """
    from pipeline.extract.flights import OpenSkyRateLimitError
    from pipeline.orchestrator import orchestrate_ingestion, SourceSyncResult

    # Mock ingest_flights_branch to raise rate limit
    monkeypatch.setattr(
        "pipeline.orchestrator.extract_opensky_flights",
        MagicMock(side_effect=OpenSkyRateLimitError("Rate limit exceeded", retry_after_seconds=3600)),
    )
    # Mock weather and disruptions to succeed
    monkeypatch.setattr(
        "pipeline.orchestrator.ingest_weather_branch",
        lambda **kwargs: SourceSyncResult(source_name="OPENMETEO_LIVE", status="SUCCESS", records_inserted=5),
    )
    monkeypatch.setattr(
        "pipeline.orchestrator.ingest_disruptions_branch",
        lambda **kwargs: SourceSyncResult(source_name="FAA_LIVE", status="SUCCESS", records_inserted=2),
    )

    result = orchestrate_ingestion(mode="live", airport_icao="KORD", dry_run=True)

    assert result.sources["flights"].status == "RATE_LIMITED"
    assert result.overall_status == "PARTIAL"
    assert "Rate limit" in result.sources["flights"].error_message


def test_live_deduplication_database_idempotent():
    """
    Test 11 & 12:
    - Repeated ingestion of the same OpenSky observation produces insert once,
      then update without creating duplicate rows.
    """
    from pipeline.database import get_db_connection
    from pipeline.transform.flights import TransformedFlight
    from pipeline.load.flights import load_flights_to_database

    conn = get_db_connection()
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    flight = TransformedFlight(
        flight_number="TEST888",
        airline_id=None,
        origin_airport_id=2,
        destination_airport_id=None,
        flight_date="2026-10-07",
        scheduled_departure=None,
        actual_departure=now,
        scheduled_arrival=None,
        actual_arrival=None,
        status="EN_ROUTE",
        departure_delay_minutes=None,
        arrival_delay_minutes=None,
        delay_category=None,
        tail_number="a88888",
        aircraft_type="A320",
        distance_miles=None,
        data_source="OPENSKY_LIVE",
        source_record_id="TEST-a88888",
    )

    try:
        # Pass 1: Insert
        m1 = load_flights_to_database(conn, [flight])
        assert m1.inserted == 1
        assert m1.updated == 0

        # Pass 2: Upsert / no duplicate
        m2 = load_flights_to_database(conn, [flight])
        assert m2.inserted == 0
        assert m2.updated == 1

        # Verify only 1 row exists
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM flights WHERE tail_number = %s AND data_source = 'OPENSKY_LIVE';",
                ("a88888",),
            )
            count = cur.fetchone()[0]
            assert count == 1
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM flights WHERE tail_number = %s AND data_source = 'OPENSKY_LIVE';", ("a88888",))
        conn.commit()
        conn.close()

