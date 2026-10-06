"""
Tests for Phase 10.1 Live Pipeline Orchestration and Fault Isolation.
Validates:
1. All three feeds succeed.
2. OpenSky fails while weather + FAA succeed (overall: PARTIAL).
3. Weather fails while OpenSky + FAA succeed (overall: PARTIAL).
4. FAA fails while OpenSky + weather succeed (overall: PARTIAL).
5. All three fail (overall: FAILED).
6. Live provenance is preserved ('OPENSKY_LIVE', 'OPENMETEO_LIVE', 'FAA_LIVE').
7. Demo records in database remain completely untouched.
8. Telemetry-only flights never receive fabricated scheduled times.
9. Telemetry-only flights never receive fabricated delay minutes.
10. operations_sync_log records telemetry correctly.
"""

from unittest.mock import patch, MagicMock
import pytest
from datetime import datetime, timezone

from pipeline.orchestrator import (
    orchestrate_ingestion,
    ingest_flights_branch,
    ingest_weather_branch,
    ingest_disruptions_branch,
)
from pipeline.transform.flights import transform_flight_records


@pytest.fixture
def sample_airport_maps():
    return (
        {"KORD": 1, "KATL": 2, "KDEN": 3, "KJFK": 4},  # ICAO
        {"ORD": 1, "ATL": 2, "DEN": 3, "JFK": 4},       # IATA
    )


@pytest.fixture
def sample_airline_maps():
    return (
        {"UAL": 1, "DAL": 2, "AAL": 3},  # ICAO
        {"UA": 1, "DL": 2, "AA": 3},     # IATA
    )


def test_orchestration_all_succeed():
    """1. All three feeds succeed in dry_run mode."""
    res = orchestrate_ingestion(mode="demo", dry_run=True)
    assert res.overall_status == "SUCCESS"
    assert res.sources["flights"].status == "SUCCESS"
    assert res.sources["weather"].status == "SUCCESS"
    assert res.sources["disruptions"].status == "SUCCESS"
    assert res.sources["flights"].records_extracted > 0
    assert res.sources["weather"].records_extracted > 0
    assert res.sources["disruptions"].records_extracted > 0


def test_orchestration_opensky_fails_partial():
    """2. OpenSky fails while weather + FAA succeed -> PARTIAL."""
    with patch("pipeline.orchestrator.extract_opensky_flights", side_effect=Exception("OpenSky Rate Limit 429")):
        with patch("pipeline.orchestrator.load_fixture_flights", side_effect=Exception("Simulated Flight Source Error")):
            res = orchestrate_ingestion(mode="demo", dry_run=True)
            assert res.overall_status == "PARTIAL"
            assert res.sources["flights"].status == "FAILED"
            assert "Simulated Flight Source Error" in res.sources["flights"].error_message
            assert res.sources["weather"].status == "SUCCESS"
            assert res.sources["disruptions"].status == "SUCCESS"


def test_orchestration_weather_fails_partial():
    """3. Weather fails while flight + disruptions succeed -> PARTIAL."""
    with patch("pipeline.orchestrator.load_weather_fixtures", side_effect=Exception("Weather API timeout")):
        res = orchestrate_ingestion(mode="demo", dry_run=True)
        assert res.overall_status == "PARTIAL"
        assert res.sources["flights"].status == "SUCCESS"
        assert res.sources["weather"].status == "FAILED"
        assert "Weather API timeout" in res.sources["weather"].error_message
        assert res.sources["disruptions"].status == "SUCCESS"


def test_orchestration_disruptions_fails_partial():
    """4. FAA disruptions fail while flights + weather succeed -> PARTIAL."""
    with patch("pipeline.orchestrator.load_news_fixtures", side_effect=Exception("FAA XML feed parse error")):
        res = orchestrate_ingestion(mode="demo", dry_run=True)
        assert res.overall_status == "PARTIAL"
        assert res.sources["flights"].status == "SUCCESS"
        assert res.sources["weather"].status == "SUCCESS"
        assert res.sources["disruptions"].status == "FAILED"
        assert "FAA XML feed parse error" in res.sources["disruptions"].error_message


def test_orchestration_all_fail():
    """5. All three sources fail -> FAILED."""
    with patch("pipeline.orchestrator.load_fixture_flights", side_effect=Exception("Flight error")), \
         patch("pipeline.orchestrator.load_weather_fixtures", side_effect=Exception("Weather error")), \
         patch("pipeline.orchestrator.load_news_fixtures", side_effect=Exception("FAA error")):
        res = orchestrate_ingestion(mode="demo", dry_run=True)
        assert res.overall_status == "FAILED"
        assert res.sources["flights"].status == "FAILED"
        assert res.sources["weather"].status == "FAILED"
        assert res.sources["disruptions"].status == "FAILED"


def test_live_provenance_preservation():
    """6. In live mode, proper data_source tags are applied."""
    mock_opensky = [
        {
            "icao24": "c01234",
            "firstSeen": 1728058500,
            "estDepartureAirport": "KORD",
            "lastSeen": 1728067320,
            "estArrivalAirport": "KDEN",
            "callsign": "UAL415",
        }
    ]
    with patch("pipeline.orchestrator.extract_opensky_flights", return_value=mock_opensky):
        flight_res = ingest_flights_branch(mode="live", dry_run=True)
        assert flight_res.status == "SUCCESS"
        assert flight_res.source_name == "OPENSKY_LIVE"


def test_demo_records_untouched_in_db():
    """7. Verifies primary demo flight 2 (UA415) remains untouched in database."""
    from pipeline.database import get_db_connection
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, flight_number, data_source, departure_delay_minutes FROM flights WHERE id = 2;")
            row = cur.fetchone()
            assert row is not None
            assert row[1] == "UA415"
            assert row[3] == 105
    finally:
        conn.close()


def test_telemetry_only_no_fabricated_scheduled_or_delay(sample_airport_maps, sample_airline_maps):
    """8 & 9. Telemetry-only OpenSky records never receive fabricated scheduled times or delay minutes."""
    airport_icao_map, airport_iata_map = sample_airport_maps
    airline_icao_map, airline_iata_map = sample_airline_maps

    raw_telemetry = [
        {
            "icao24": "ab12cd",
            "firstSeen": 1728058500,  # 2024-10-04 16:15:00 UTC
            "lastSeen": 1728067320,
            "estDepartureAirport": "KORD",
            "estArrivalAirport": "KDEN",
            "callsign": "UAL415",
            # Note: No 'scheduledDeparture', no 'scheduledArrival', no 'delayCategory'
        }
    ]

    report = transform_flight_records(
        raw_records=raw_telemetry,
        airport_icao_map=airport_icao_map,
        airport_iata_map=airport_iata_map,
        airline_icao_map=airline_icao_map,
        airline_iata_map=airline_iata_map,
        data_source="OPENSKY_LIVE",
    )

    assert report.total_transformed == 1
    t_flight = report.transformed[0]

    # Verify no fabricated commercial scheduled departure or arrival
    assert t_flight.scheduled_departure is None
    assert t_flight.scheduled_arrival is None

    # Verify no fabricated commercial delay
    assert t_flight.departure_delay_minutes is None
    assert t_flight.arrival_delay_minutes is None
    # Verify no fabricated carrier delay category
    assert t_flight.delay_category is None
    # Verify source provenance tag
    assert t_flight.data_source == "OPENSKY_LIVE"
    # Verify tail_number matches icao24
    assert t_flight.tail_number == "ab12cd"


def test_telemetry_only_intelligence_evaluation():
    """Verify intelligence candidate generation honors telemetry-only semantics."""
    from pipeline.intelligence.evidence import FlightDetail
    from pipeline.intelligence.candidate_generation import generate_candidates_for_flight

    telemetry_detail = FlightDetail(
        flight_id=9999,
        flight_number="UAL415",
        airline_id=3,
        airline_name="United Airlines",
        airline_iata="UA",
        origin_airport_id=2,
        origin_iata="ORD",
        origin_name="Chicago O'Hare",
        destination_airport_id=4,
        destination_iata="DEN",
        destination_name="Denver Intl",
        flight_date="2024-10-04",
        scheduled_departure=None,
        scheduled_arrival=None,
        actual_departure=None,
        actual_arrival=None,
        status="EN_ROUTE",
        departure_delay_minutes=None,
        arrival_delay_minutes=None,
        delay_category=None,
        tail_number="ab12cd",
        aircraft_type=None,
    )

    from pipeline.intelligence.evidence import FlightEvidenceBundle

    bundle = FlightEvidenceBundle(
        flight=telemetry_detail,
        weather_observations=[],
        disruptions=[],
        flight_events=[],
    )

    result = generate_candidates_for_flight(bundle)

    assert result.is_on_time is False
    assert result.primary_candidate == "INSUFFICIENT_EVIDENCE / LIVE_TELEMETRY_ONLY"
    assert result.candidates == []


def test_operations_sync_log_recorded():
    """10. Sync log writes an entry to database."""
    from pipeline.database import get_db_connection
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations_sync_log;")
            count_before = cur.fetchone()[0]

        orchestrate_ingestion(mode="demo", dry_run=True)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM operations_sync_log;")
            count_after = cur.fetchone()[0]

        assert count_after >= count_before + 3
    finally:
        conn.close()


def test_live_upsert_cannot_overwrite_demo_row():
    """Verify live telemetry cannot overwrite or mutate an existing DEMO/fixture flight."""
    from datetime import datetime, timezone
    from pipeline.database import get_db_connection
    from pipeline.load.flights import load_flights_to_database
    from pipeline.transform.flights import TransformedFlight

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Query existing UA415 demo row
            cur.execute("SELECT flight_number, airline_id, scheduled_departure, departure_delay_minutes FROM flights WHERE id = 2;")
            ua_row = cur.fetchone()
            assert ua_row is not None
            sched_dep = ua_row[2]

        # Construct a live telemetry record attempting to collide with UA415
        live_telemetry = TransformedFlight(
            flight_number="UA415",
            airline_id=3,
            origin_airport_id=2,
            destination_airport_id=4,
            flight_date="2026-10-04",
            scheduled_departure=None,  # Live telemetry has NULL schedule
            actual_departure=datetime(2026, 10, 4, 21, 45, tzinfo=timezone.utc),
            scheduled_arrival=None,
            actual_arrival=None,
            status="EN_ROUTE",
            departure_delay_minutes=None,
            arrival_delay_minutes=None,
            delay_category=None,
            tail_number="TEST_TAIL_999",
            aircraft_type="B738",
            distance_miles=900.0,
            data_source="OPENSKY_LIVE",
            source_record_id="test_live_coll_1",
        )

        load_flights_to_database(conn, [live_telemetry], dry_run=False)

        # Verify UA415 remains 100% untouched
        with conn.cursor() as cur:
            cur.execute("SELECT flight_number, data_source, scheduled_departure, departure_delay_minutes FROM flights WHERE id = 2;")
            after_row = cur.fetchone()
            assert after_row[0] == "UA415"
            assert after_row[1] == "FLIGHTAWARE"
            assert after_row[2] == sched_dep
            assert after_row[3] == 105

            # Cleanup test record
            cur.execute("DELETE FROM flights WHERE tail_number = 'TEST_TAIL_999' AND data_source = 'OPENSKY_LIVE';")
        conn.commit()
    finally:
        conn.close()


def test_live_telemetry_idempotence_and_two_observations():
    """Verify live telemetry re-ingestion is idempotent and distinct observations for same aircraft are preserved."""
    from datetime import datetime, timezone
    from pipeline.database import get_db_connection
    from pipeline.load.flights import load_flights_to_database
    from pipeline.transform.flights import TransformedFlight

    conn = get_db_connection()
    try:
        t1 = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)

        obs1 = TransformedFlight(
            flight_number="UA101",
            airline_id=3,
            origin_airport_id=2,
            destination_airport_id=4,
            flight_date="2026-10-05",
            scheduled_departure=None,
            actual_departure=t1,
            scheduled_arrival=None,
            actual_arrival=None,
            status="EN_ROUTE",
            departure_delay_minutes=None,
            arrival_delay_minutes=None,
            delay_category=None,
            tail_number="NTEST01",
            aircraft_type="A320",
            distance_miles=None,
            data_source="OPENSKY_LIVE",
            source_record_id="test_obs_1",
        )

        # 1. First insert
        m1 = load_flights_to_database(conn, [obs1], dry_run=False)
        assert m1.inserted == 1

        # 2. Re-insert same record (idempotency -> updated/no-op, 0 errors)
        m2 = load_flights_to_database(conn, [obs1], dry_run=False)
        assert m2.updated == 1
        assert m2.errors == 0

        # 3. Second distinct observation for same aircraft at different departure time
        obs2 = TransformedFlight(
            flight_number="UA102",
            airline_id=3,
            origin_airport_id=4,
            destination_airport_id=2,
            flight_date="2026-10-05",
            scheduled_departure=None,
            actual_departure=t2,
            scheduled_arrival=None,
            actual_arrival=None,
            status="EN_ROUTE",
            departure_delay_minutes=None,
            arrival_delay_minutes=None,
            delay_category=None,
            tail_number="NTEST01",
            aircraft_type="A320",
            distance_miles=None,
            data_source="OPENSKY_LIVE",
            source_record_id="test_obs_2",
        )
        m3 = load_flights_to_database(conn, [obs2], dry_run=False)
        assert m3.inserted == 1

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM flights WHERE tail_number = 'NTEST01' AND data_source = 'OPENSKY_LIVE';")
            count = cur.fetchone()[0]
            assert count == 2

            # Cleanup
            cur.execute("DELETE FROM flights WHERE tail_number = 'NTEST01' AND data_source = 'OPENSKY_LIVE';")
        conn.commit()
    finally:
        conn.close()


def test_weather_and_faa_live_provenance():
    """Verify live branches produce OPENMETEO_LIVE and FAA_LIVE data_source values."""
    from pipeline.transform.weather import transform_weather_records
    from pipeline.transform.news import transform_news_records

    # Weather transformation
    wx_raw = [{
        "airport_code": "KORD",
        "time": "2024-10-04T16:15:00Z",
        "temperature_c": 18.5,
        "dewpoint_c": 10.0,
        "wind_speed_knots": 12.0,
        "wind_gust_knots": 18.0,
        "wind_direction_deg": 270,
        "visibility_miles": 10.0,
        "weather_code": 3,
    }]
    coords = {"KORD": {"id": 2, "latitude": 41.97, "longitude": -87.90}}
    wx_rep = transform_weather_records(wx_raw, coords, data_source="OPENMETEO_LIVE")
    assert wx_rep.total_transformed == 1
    assert wx_rep.transformed[0].data_source == "OPENMETEO_LIVE"

    # FAA disruption transformation
    faa_raw = [{
        "title": "Ground Stop ORD",
        "detail": "Advisory for ORD",
        "airport_code": "ORD",
        "raw_type": "Ground Stop",
        "severity": "HIGH",
        "start_time": "2024-10-04T16:00:00Z",
    }]
    news_rep = transform_news_records(faa_raw, {"ORD": 2}, {}, data_source="FAA_LIVE")
    assert news_rep.total_transformed == 1
    assert news_rep.transformed[0].data_source == "FAA_LIVE"

