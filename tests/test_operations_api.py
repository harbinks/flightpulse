"""
Comprehensive test suite for FlightPulse Operations API (Phase 10.3).
Tests:
1. GET /operations/status reflects operations_sync_log records.
2. NEVER_SYNCED state is returned when a source has no sync log history.
3. Successful, failed, and partial sync entries are reflected accurately.
4. POST /operations/sync triggers the orchestrator without duplicating logic.
5. POST /operations/sync returns structured per-source metrics.
6. Concurrency protection prevents simultaneous sync runs (HTTP 409 SYNC_IN_PROGRESS).
7. Source-level failure isolation (OpenSky failure does not corrupt Weather/FAA reporting).
8. Mode validation rejects invalid flight mode with HTTP 422.
9. Flight queries default to DEMO mode and isolate LIVE mode.
10. Preservation of UA415 and existing endpoints.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from pipeline.orchestrator import OrchestrationResult, SourceSyncResult

client = TestClient(app)


# ============================================================================
# 1. Flight Mode API Validation (422 and isolation)
# ============================================================================

def test_flight_mode_invalid_returns_422():
    """Verify passing an unrecognized mode returns HTTP 422."""
    response = client.get("/flights?mode=invalid_mode")
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower()


def test_flight_mode_default_and_demo():
    """Verify default query and mode=demo return only DEMO/FIXTURE records."""
    # Default
    r_def = client.get("/flights")
    assert r_def.status_code == 200
    for f in r_def.json()["flights"]:
        assert f.get("data_source") in ("DEMO", "FIXTURE", "FIXTURE_REPLAY", "FLIGHTAWARE")

    # Explicit demo
    r_demo = client.get("/flights?mode=demo")
    assert r_demo.status_code == 200
    for f in r_demo.json()["flights"]:
        assert f.get("data_source") != "OPENSKY_LIVE"


def test_flight_mode_live():
    """Verify mode=live query returns only OPENSKY_LIVE records."""
    r_live = client.get("/flights?mode=live")
    assert r_live.status_code == 200
    for f in r_live.json()["flights"]:
        assert f.get("data_source") == "OPENSKY_LIVE"


# ============================================================================
# 2. Operations Status Endpoint (/operations/status)
# ============================================================================

def test_operations_status_schema_and_keys():
    """Verify GET /operations/status returns required structural schema."""
    response = client.get("/operations/status")
    assert response.status_code == 200
    data = response.json()

    assert "overall_status" in data
    assert data["overall_status"] in ("HEALTHY", "PARTIAL", "FAILED", "NEVER_SYNCED")
    assert "sources" in data

    for src_name in ("opensky", "openmeteo", "faa"):
        assert src_name in data["sources"]
        src = data["sources"][src_name]
        assert "status" in src
        assert src["status"] in ("SUCCESS", "FAILED", "NEVER_SYNCED", "SKIPPED")
        assert "records_extracted" in src
        assert "records_inserted" in src
        assert "records_updated" in src
        assert "duration_ms" in src


def test_operations_status_never_synced_behavior():
    """Verify NEVER_SYNCED is returned when no matching records exist in log."""
    from pipeline.database import get_db_connection
    from app.services.operations_service import get_operations_status

    # Test via mock cursor returning no rows
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None

    status_resp = get_operations_status(mock_conn)
    assert status_resp.overall_status == "NEVER_SYNCED"
    assert status_resp.last_sync is None
    for src in status_resp.sources.values():
        assert src.status == "NEVER_SYNCED"
        assert src.last_attempt is None
        assert src.last_success is None


def test_operations_status_reflects_failed_and_partial():
    """Verify status correctly reflects FAILED and PARTIAL when individual sources fail."""
    from app.services.operations_service import get_operations_status

    # Mock cursor to return a failure for opensky and success for others
    now = datetime.now(timezone.utc)
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Sequence of fetchone: (attempt, success) for opensky, openmeteo, faa
    mock_cur.fetchone.side_effect = [
        # opensky attempt (FAILED)
        ("FAILED", now, 0, 0, 0, 50.0, "API Timeout"),
        # opensky latest success (None)
        None,
        # openmeteo attempt (SUCCESS)
        ("SUCCESS", now, 4, 4, 0, 20.0, None),
        # openmeteo latest success
        (now,),
        # faa attempt (SUCCESS)
        ("SUCCESS", now, 7, 7, 0, 30.0, None),
        # faa latest success
        (now,),
    ]

    status_resp = get_operations_status(mock_conn)
    assert status_resp.overall_status == "PARTIAL"
    assert status_resp.sources["opensky"].status == "FAILED"
    assert status_resp.sources["opensky"].error_message == "API Timeout"
    assert status_resp.sources["openmeteo"].status == "SUCCESS"
    assert status_resp.sources["faa"].status == "SUCCESS"


# ============================================================================
# 3. On-Demand Sync Endpoint (POST /operations/sync)
# ============================================================================

def test_operations_sync_endpoint_triggers_orchestrator():
    """Verify POST /operations/sync delegates to orchestrate_ingestion."""
    now = datetime.now(timezone.utc)
    mock_orch_res = OrchestrationResult(
        overall_status="SUCCESS",
        sources={
            "flights": SourceSyncResult(
                source_name="OPENSKY_LIVE",
                status="SUCCESS",
                records_extracted=12,
                records_transformed=10,
                records_inserted=10,
                records_updated=0,
                duration_ms=45.0,
                timestamp=now,
            ),
            "weather": SourceSyncResult(
                source_name="OPENMETEO_LIVE",
                status="SUCCESS",
                records_extracted=4,
                records_transformed=4,
                records_inserted=4,
                records_updated=0,
                duration_ms=25.0,
                timestamp=now,
            ),
            "disruptions": SourceSyncResult(
                source_name="FAA_LIVE",
                status="SUCCESS",
                records_extracted=2,
                records_transformed=2,
                records_inserted=2,
                records_updated=0,
                duration_ms=30.0,
                timestamp=now,
            ),
        },
        duration_ms=100.0,
        timestamp=now,
    )

    with patch("app.services.operations_service.orchestrate_ingestion", return_value=mock_orch_res) as mock_orch:
        response = client.post("/operations/sync?mode=live&dry_run=true")
        assert response.status_code == 200
        mock_orch.assert_called_once_with(
            mode="live",
            airport_icao="KORD",
            dry_run=True,
        )

        data = response.json()
        assert data["overall_status"] == "SUCCESS"
        assert "flights" in data["sources"]
        assert data["sources"]["flights"]["records_extracted"] == 12
        assert data["sources"]["flights"]["records_inserted"] == 10
        assert data["sources"]["weather"]["records_extracted"] == 4
        assert data["sources"]["disruptions"]["records_extracted"] == 2


def test_operations_sync_source_failure_isolation():
    """Verify an OpenSky failure in sync returns PARTIAL status without crashing."""
    now = datetime.now(timezone.utc)
    mock_orch_res = OrchestrationResult(
        overall_status="PARTIAL",
        sources={
            "flights": SourceSyncResult(
                source_name="OPENSKY_LIVE",
                status="FAILED",
                records_extracted=0,
                errors=1,
                error_message="OpenSky API HTTP 429",
                duration_ms=50.0,
                timestamp=now,
            ),
            "weather": SourceSyncResult(
                source_name="OPENMETEO_LIVE",
                status="SUCCESS",
                records_extracted=4,
                records_transformed=4,
                records_inserted=4,
                duration_ms=25.0,
                timestamp=now,
            ),
            "disruptions": SourceSyncResult(
                source_name="FAA_LIVE",
                status="SUCCESS",
                records_extracted=2,
                records_transformed=2,
                records_inserted=2,
                duration_ms=30.0,
                timestamp=now,
            ),
        },
        duration_ms=105.0,
        timestamp=now,
    )

    with patch("app.services.operations_service.orchestrate_ingestion", return_value=mock_orch_res):
        response = client.post("/operations/sync?mode=live")
        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "PARTIAL"
        assert data["sources"]["flights"]["status"] == "FAILED"
        assert "429" in data["sources"]["flights"]["error_message"]
        assert data["sources"]["weather"]["status"] == "SUCCESS"
        assert data["sources"]["disruptions"]["status"] == "SUCCESS"


def test_operations_sync_concurrency_lock():
    """Verify simultaneous sync requests return HTTP 409 SYNC_IN_PROGRESS."""
    import app.services.operations_service as ops_mod

    # Artificially engage lock
    ops_mod._SYNC_IN_PROGRESS = True
    try:
        response = client.post("/operations/sync?mode=live")
        assert response.status_code == 409
        data = response.json()
        assert "already in progress" in data["detail"].lower()
    finally:
        ops_mod._SYNC_IN_PROGRESS = False


def test_operations_sync_invalid_mode_rejected():
    """Verify POST /operations/sync rejects invalid mode parameter with 422."""
    response = client.post("/operations/sync?mode=unknown_mode")
    assert response.status_code == 422
    assert "invalid" in response.json()["detail"].lower()


# ============================================================================
# 4. Invariant Protection: UA415 & Existing Endpoints Intact
# ============================================================================

def test_ua415_and_intelligence_endpoints_intact():
    """Verify Flight 2 (UA415), intelligence, and AI endpoints continue to operate."""
    # 1. Flight detail
    f2_resp = client.get("/flights/2")
    assert f2_resp.status_code == 200
    f2_data = f2_resp.json()
    assert f2_data["flight_number"] == "UA415"
    assert f2_data["departure_delay_minutes"] == 105
    assert f2_data["scheduled_departure"] is not None

    # 2. Intelligence
    intel_resp = client.get("/flights/2/intelligence")
    assert intel_resp.status_code == 200
    intel_data = intel_resp.json()
    assert "ATC / WEATHER INTERACTION" in intel_data["primary_candidate"]["category"]

    # 3. AI analysis
    ai_resp = client.get("/flights/2/ai-analysis")
    assert ai_resp.status_code == 200
    ai_data = ai_resp.json()
    assert ai_data["flight_number"] == "UA415"
    assert ai_data["status"] in ("success", "unavailable")
