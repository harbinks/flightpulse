"""
Comprehensive test suite for Grounded AI Analyst service and Ollama integration.
Validates client configuration, mocking, timeout handling, fallback mechanisms,
API route integration, and prompt grounding constraints.
"""

import json
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.ai import AIAnalystOutput, FlightAIAnalysisResponse, GroundedEvidenceContext
from app.services.ai_analyst import (
    SYSTEM_PROMPT,
    analyze_flight_with_ai,
    assemble_grounded_context,
    build_grounded_prompt,
    generate_deterministic_fallback,
)
from app.services.ollama_service import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from pipeline.config import config
from pipeline.database import get_db_connection

client = TestClient(app)


# ============================================================================
# 1. Ollama Configuration Tests
# ============================================================================

def test_ollama_configuration():
    """Verify Ollama configuration defaults and environment loading."""
    assert config.ollama.base_url.startswith("http")
    assert len(config.ollama.model) > 0
    assert config.ollama.timeout_sec > 0

    custom_client = OllamaClient(
        base_url="http://custom-host:11434",
        model="custom-model:latest",
        timeout=15.0,
    )
    assert custom_client.base_url == "http://custom-host:11434"
    assert custom_client.model == "custom-model:latest"
    assert custom_client.timeout == 15.0


# ============================================================================
# 2. Ollama Client Success (Mocked)
# ============================================================================

def test_ollama_client_success():
    """Verify OllamaClient correctly calls API and returns completion."""
    mock_payload = {
        "summary": "Delayed due to thunderstorms at ORD.",
        "primary_cause": "WEATHER",
        "confidence": "HIGH",
        "explanation": "Severe storm observed at 20:21 UTC.",
        "evidence_used": ["Thunderstorm at ORD"],
        "limitations": ["None"],
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": json.dumps(mock_payload)}

    with patch.object(httpx.Client, "post", return_value=mock_response):
        c = OllamaClient(base_url="http://localhost:11434", model="llama3:latest")
        result = c.generate(prompt="Explain flight delay", system_prompt="You are analyst")
        data = json.loads(result)
        assert data["primary_cause"] == "WEATHER"
        assert data["confidence"] == "HIGH"


# ============================================================================
# 3. Ollama Unavailable (Connection Failure)
# ============================================================================

def test_ollama_unavailable():
    """Verify OllamaConnectionError raised when daemon is offline."""
    with patch.object(httpx.Client, "post", side_effect=httpx.ConnectError("Connection refused")):
        c = OllamaClient(base_url="http://localhost:11434")
        with pytest.raises(OllamaConnectionError):
            c.generate(prompt="Test prompt")


# ============================================================================
# 4. Ollama Timeout Handling
# ============================================================================

def test_ollama_timeout():
    """Verify OllamaTimeoutError raised on generation timeout."""
    with patch.object(httpx.Client, "post", side_effect=httpx.TimeoutException("Request timed out")):
        c = OllamaClient(base_url="http://localhost:11434", timeout=5.0)
        with pytest.raises(OllamaTimeoutError):
            c.generate(prompt="Test prompt")


# ============================================================================
# 5. Invalid/Malformed Response Handling & Fallback
# ============================================================================

def test_invalid_ollama_response_fallback():
    """Verify malformed JSON from Ollama triggers safe deterministic fallback."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.model = "test-model"
    mock_client.generate.return_value = "NOT A JSON STRING --- INVALID OUTPUT"

    conn = get_db_connection()
    try:
        response = analyze_flight_with_ai(conn, flight_id=2, client=mock_client)
        assert response is not None
        assert response.status == "error"
        assert response.is_grounded is True
        # Authoritative deterministic findings preserved
        assert response.analysis.primary_cause == "ATC / WEATHER INTERACTION"
        assert response.analysis.confidence == "HIGH"
        assert any("malformed" in lim.lower() for lim in response.analysis.limitations)
    finally:
        conn.close()


# ============================================================================
# 6. Valid Structured AI Response Validation
# ============================================================================

def test_valid_structured_ai_response():
    """Verify valid model response correctly parses into FlightAIAnalysisResponse."""
    mock_ai_json = {
        "summary": "Flight UA415 delayed due to ORD convective storm and FAA ground stop.",
        "primary_cause": "ATC / WEATHER INTERACTION",
        "confidence": "HIGH",
        "explanation": "At 20:21 UTC, ORD weather station logged thunderstorms with 42kt gusts while FAA instituted a full ground stop.",
        "evidence_used": ["METAR thunderstorm at ORD", "FAA Ground Stop active 19:45-21:30 UTC"],
        "limitations": ["Airline gate log did not record maintenance turnaround."],
    }
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.model = "llama3:latest"
    mock_client.generate.return_value = json.dumps(mock_ai_json)

    conn = get_db_connection()
    try:
        res = analyze_flight_with_ai(conn, flight_id=2, client=mock_client)
        assert res is not None
        assert res.status == "success"
        assert res.flight_id == 2
        assert res.flight_number == "UA415"
        assert res.analysis.primary_cause == "ATC / WEATHER INTERACTION"
        assert res.analysis.confidence == "HIGH"
        assert len(res.analysis.evidence_used) == 2
        assert len(res.analysis.limitations) == 1
    finally:
        conn.close()


# ============================================================================
# 7. Flight AI Endpoint (FastAPI GET /flights/{id}/ai-analysis)
# ============================================================================

def test_flight_ai_endpoint_success():
    """Verify GET /flights/{flight_id}/ai-analysis endpoint returns 200 and schema."""
    mock_ai_json = {
        "summary": "Flight UA415 delay of 105 min attributed to ATC / Weather Interaction.",
        "primary_cause": "ATC / WEATHER INTERACTION",
        "confidence": "HIGH",
        "explanation": "Severe thunderstorm compounded with FAA Ground Stop.",
        "evidence_used": ["ORD Thunderstorm", "FAA Ground Stop"],
        "limitations": ["None"],
    }
    with patch("app.services.ai_analyst.ollama_client.generate", return_value=json.dumps(mock_ai_json)):
        resp = client.get("/flights/2/ai-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("success", "unavailable")
        assert data["flight_id"] == 2
        assert data["flight_number"] == "UA415"
        assert "analysis" in data
        assert "primary_cause" in data["analysis"]
        assert "deterministic_attribution" in data


# ============================================================================
# 8. Unknown Flight ID (404 Not Found)
# ============================================================================

def test_flight_ai_endpoint_not_found():
    """Verify non-existent flight returns 404 Not Found."""
    resp = client.get("/flights/99999/ai-analysis")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ============================================================================
# 9. Deterministic Intelligence Without Ollama (Offline Graceful Fallback)
# ============================================================================

def test_deterministic_intelligence_without_ollama():
    """Verify system remains fully operational and returns deterministic analysis when Ollama is offline."""
    mock_client = MagicMock(spec=OllamaClient)
    mock_client.generate.side_effect = OllamaConnectionError("Daemon offline")

    conn = get_db_connection()
    try:
        res = analyze_flight_with_ai(conn, flight_id=2, client=mock_client)
        assert res is not None
        assert res.status == "unavailable"
        assert res.flight_number == "UA415"
        assert res.analysis.primary_cause == "ATC / WEATHER INTERACTION"
        assert res.analysis.confidence == "HIGH"
        assert any("offline" in lim.lower() or "unreachable" in lim.lower() for lim in res.analysis.limitations)
        assert res.deterministic_attribution["cause"] == "ATC / WEATHER INTERACTION"
    finally:
        conn.close()


# ============================================================================
# 10. Prompt Grounding Rules Verification
# ============================================================================

def test_prompt_grounding_rules():
    """Verify system and user prompt templates contain strict grounding directives."""
    # Check system prompt directives
    assert "absolute authority" in SYSTEM_PROMPT.lower()
    assert "strict grounding rules" in SYSTEM_PROMPT.lower()
    assert "do not invent" in SYSTEM_PROMPT.lower()
    assert "do not fabricate" in SYSTEM_PROMPT.lower()

    # Check assembled context and prompt
    conn = get_db_connection()
    try:
        ctx = assemble_grounded_context(conn, flight_id=2)
        assert ctx is not None
        user_prompt = build_grounded_prompt(ctx)

        # Prompt must include authoritative findings
        assert "AUTHORITATIVE DETERMINISTIC ENGINE FINDINGS" in user_prompt
        assert ctx.deterministic_cause in user_prompt
        assert ctx.flight_number in user_prompt
        assert "SUPPORTING EVIDENCE IDENTIFIED BY ENGINE" in user_prompt
        assert "METEOROLOGICAL OBSERVATIONS" in user_prompt
        assert "FAA AIR TRAFFIC MANAGEMENT DISRUPTIONS" in user_prompt
    finally:
        conn.close()


# ============================================================================
# 11. AI Cache & Concurrency Deduplication Verification
# ============================================================================

def test_ai_cache_and_deduplication():
    """Verify that successful AI syntheses are cached in-memory and return instantly."""
    from app.services.ai_analyst import clear_ai_cache, _ANALYSIS_CACHE

    clear_ai_cache()
    mock_payload = {
        "summary": "Delayed due to thunderstorms at ORD.",
        "primary_cause": "ATC / WEATHER INTERACTION",
        "confidence": "HIGH",
        "explanation": "Severe storm observed at 20:21 UTC.",
        "evidence_used": ["Thunderstorm at ORD"],
        "limitations": ["None"],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": json.dumps(mock_payload)}

    conn = get_db_connection()
    try:
        with patch.object(httpx.Client, "post", return_value=mock_resp) as mock_post:
            # First call executes inference and populates cache
            res1 = analyze_flight_with_ai(conn, flight_id=2, use_cache=True)
            assert res1 is not None
            assert res1.status == "success"
            assert mock_post.call_count == 1
            assert 2 in _ANALYSIS_CACHE

            # Second call retrieves directly from cache with zero additional HTTP posts
            res2 = analyze_flight_with_ai(conn, flight_id=2, use_cache=True)
            assert res2 is not None
            assert res2.status == "success"
            assert mock_post.call_count == 1  # Unchanged!
            assert res2.analysis.summary == res1.analysis.summary
    finally:
        clear_ai_cache()
        conn.close()
