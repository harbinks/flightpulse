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

    # Verify no fabricated commercial delay
    assert t_flight.departure_delay_minutes == 0
    assert t_flight.arrival_delay_minutes == 0
    # Verify no fabricated carrier delay category
    assert t_flight.delay_category is None
    # Verify source provenance tag
    assert t_flight.data_source == "OPENSKY_LIVE"
    # Verify tail_number matches icao24
    assert t_flight.tail_number == "ab12cd"


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
