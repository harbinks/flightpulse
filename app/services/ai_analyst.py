"""
Grounded AI Analyst Service.
Constructs strict evidence-grounded prompts from database records and the deterministic
intelligence engine, coordinates Ollama local LLM inference, validates structured outputs,
and guarantees seamless fallback to deterministic attribution if Ollama is unavailable.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from psycopg2.extensions import connection

from app.schemas.ai import (
    AIAnalystOutput,
    FlightAIAnalysisResponse,
    GroundedEvidenceContext,
)
from app.services.flight_service import (
    get_flight_by_id,
    get_flight_disruptions,
    get_flight_weather,
)
from app.services.intelligence_service import get_flight_intelligence
from app.services.ollama_service import (
    OllamaClient,
    OllamaClientError,
    OllamaConnectionError,
    OllamaTimeoutError,
    ollama_client,
)
from app.services.timeline_service import build_flight_timeline

logger = logging.getLogger("flightpulse.ai.analyst")

SYSTEM_PROMPT = """You are the FlightPulse Aviation Analyst, an expert air traffic operations intelligence assistant.
Explain flight delays using ONLY the supplied factual evidence from METAR observations, FAA ATCSCC notices, and dispatch logs.

STRICT GROUNDING RULES:
1. The DETERMINISTIC RESULT is the absolute authority. You MUST NOT overturn, contradict, or alter the attributed primary cause or confidence level.
2. Cite ONLY supplied flight facts, weather records, and FAA notices. DO NOT invent facts, weather conditions, wind speeds, mechanical failures, crew issues, or causes.
3. Distinguish clearly between the carrier-reported category (unverified upstream claim) and the inferred candidate cause (evidence-backed finding).
4. If evidence is insufficient, explicitly state that available data does not explain the delay.
5. Do not fabricate timestamps or statistics.

OUTPUT FORMAT:
Respond with a strictly valid JSON object matching this schema:
{
  "summary": "1-sentence executive briefing summarizing the flight, route, delay duration, and primary cause.",
  "primary_cause": "The primary cause matching the deterministic finding exactly.",
  "confidence": "The confidence level matching the deterministic finding (HIGH, MEDIUM, LOW, or INSUFFICIENT).",
  "explanation": "2 concise sentences explaining how the specific weather and ATC advisories correlated with the departure delay.",
  "evidence_used": [
    "Specific factual data point cited from the dossier"
  ],
  "limitations": [
    "Operational uncertainties, unverified airline claims, or time gaps in available logs"
  ]
}
Do NOT include markdown formatting or extra commentary outside the JSON object."""


def assemble_grounded_context(conn: connection, flight_id: int) -> Optional[GroundedEvidenceContext]:
    """
    Gather and assemble all verified database records and deterministic intelligence
    into a structured grounded context bundle.
    """
    flight = get_flight_by_id(conn, flight_id)
    if not flight:
        return None

    intel = get_flight_intelligence(conn, flight_id)
    weather = get_flight_weather(conn, flight_id)
    disruptions = get_flight_disruptions(conn, flight_id)
    timeline = build_flight_timeline(conn, flight_id)

    # Weather observations summary strings
    weather_strings: List[str] = []
    if weather and weather.origin_observations:
        for obs in weather.origin_observations[:5]:
            t_str = obs.observation_time.strftime("%H:%M UTC") if obs.observation_time else "Unknown"
            w_str = (
                f"[{t_str} at {obs.airport_code}] Condition: {obs.condition_code}, "
                f"Temp: {obs.temperature_c}C, Wind: {obs.wind_speed_knots}kts (Gusts: {obs.wind_gust_knots or 0}kts), "
                f"Vis: {obs.visibility_miles}mi"
            )
            weather_strings.append(w_str)

    # FAA disruptions summary strings
    disruption_strings: List[str] = []
    if disruptions and disruptions.disruptions:
        for d in disruptions.disruptions:
            apt = d.affected_airport_code or "Route"
            desc = d.summary or ""
            d_str = f"[{d.event_type} - Severity: {d.severity}] {d.title} (Airport: {apt}): {desc}"
            disruption_strings.append(d_str)

    # Timeline milestone summary strings
    timeline_strings: List[str] = []
    if timeline and timeline.timeline:
        for ev in timeline.timeline[:10]:
            t_str = ev.time.strftime("%H:%M UTC") if ev.time else "Unknown"
            timeline_strings.append(f"[{t_str}] [{ev.category}] {ev.title}: {ev.detail or ''}")

    # Candidate causes from engine
    candidate_list: List[Dict[str, Any]] = []
    supporting_evidence: List[str] = []
    det_cause = "UNKNOWN / INSUFFICIENT_EVIDENCE"
    det_confidence = "INSUFFICIENT"
    det_score = 0.0

    if intel:
        if intel.primary_candidate:
            det_cause = intel.primary_candidate.category
            det_confidence = intel.primary_candidate.confidence
            det_score = intel.primary_candidate.score

        for c in intel.candidates:
            candidate_list.append({
                "category": c.category,
                "score": c.score,
                "confidence": c.confidence,
                "primary_signal": c.primary_signal,
                "evidence": c.evidence,
            })
            if c.category == det_cause or "INTERACTION" in det_cause or c.score >= 0.5:
                for ev in c.evidence:
                    if ev not in supporting_evidence:
                        supporting_evidence.append(ev)

    return GroundedEvidenceContext(
        flight_id=flight.id,
        flight_number=flight.flight_number,
        airline=flight.airline_name,
        route=f"{flight.origin_iata} -> {flight.destination_iata}",
        flight_date=flight.flight_date,
        scheduled_departure=flight.scheduled_departure.isoformat() if flight.scheduled_departure else "N/A",
        actual_departure=flight.actual_departure.isoformat() if flight.actual_departure else None,
        departure_delay_minutes=flight.departure_delay_minutes,
        status=flight.status,
        reported_delay_category=flight.delay_category,
        deterministic_cause=det_cause,
        deterministic_confidence=det_confidence,
        deterministic_score=det_score,
        candidate_causes=candidate_list,
        supporting_evidence=supporting_evidence,
        weather_observations=weather_strings,
        faa_disruptions=disruption_strings,
        timeline_milestones=timeline_strings,
    )


def build_grounded_prompt(context: GroundedEvidenceContext) -> str:
    """
    Construct a concise, factual user prompt detailing the authoritative deterministic attribution
    and strictly bound evidence bundle.
    """
    prompt = f"""FLIGHT OPERATIONS DOSSIER:
- Flight: {context.flight_number} ({context.airline}) | Route: {context.route}
- Scheduled Departure: {context.scheduled_departure} | Actual: {context.actual_departure or 'N/A'}
- Departure Delay: {context.departure_delay_minutes} minutes ({context.status})
- Carrier-Reported Reason: {context.reported_delay_category or 'NONE'}

AUTHORITATIVE DETERMINISTIC ENGINE FINDINGS:
- Inferred Primary Cause: {context.deterministic_cause}
- Confidence Level: {context.deterministic_confidence}
- Evaluation Score: {context.deterministic_score:.2f}

SUPPORTING EVIDENCE IDENTIFIED BY ENGINE:
"""
    if context.supporting_evidence:
        for ev in context.supporting_evidence[:3]:
            prompt += f"  * {ev}\n"
    else:
        prompt += "  * No corroborating meteorological or air traffic advisories found.\n"

    prompt += "\nMETEOROLOGICAL OBSERVATIONS (METAR AT ORIGIN):\n"
    if context.weather_observations:
        for w in context.weather_observations[:2]:
            prompt += f"  * {w}\n"
    else:
        prompt += "  * No abnormal weather records logged in the temporal window.\n"

    prompt += "\nFAA AIR TRAFFIC MANAGEMENT DISRUPTIONS & NOTICES:\n"
    if context.faa_disruptions:
        for d in context.faa_disruptions[:2]:
            prompt += f"  * {d}\n"
    else:
        prompt += "  * Zero active FAA ground stops or NAS flow delay programs logged.\n"

    prompt += "\nTask: Synthesize this dossier into the required JSON format. Ground every sentence in the facts above."
    return prompt


def generate_deterministic_fallback(
    context: GroundedEvidenceContext,
    reason: str,
) -> FlightAIAnalysisResponse:
    """
    Generate a reliable, structured fallback response when Ollama is offline or encounters an error.
    Preserves 100% of deterministic intelligence and alerts the client safely without HTTP 500.
    """
    if "LIVE_TELEMETRY_ONLY" in context.deterministic_cause or context.departure_delay_minutes is None:
        summary = f"Flight {context.flight_number} currently monitored via live ADS-B telemetry without published commercial schedule."
        explanation = "This flight is an active OpenSky live telemetry observation. Scheduled departure time and delay minutes are unestablished or pending commercial schedule pairing."
    elif context.deterministic_cause == "ON_TIME / OPERATIONAL_TOLERANCE":
        summary = f"Flight {context.flight_number} operated within standard operational schedule with {context.departure_delay_minutes or 0} minutes delay."
        explanation = "The flight departure conformed to standard air traffic and airline scheduling tolerance with no significant adverse signals."
    elif context.deterministic_cause == "UNKNOWN / INSUFFICIENT_EVIDENCE":
        summary = f"Flight {context.flight_number} experienced a {context.departure_delay_minutes or 0}-minute delay with insufficient external corroborating evidence."
        explanation = f"Although delayed by {context.departure_delay_minutes or 0} minutes, no severe convective weather, FAA ground stops, or major hub outages matched the departure window. The carrier-reported category was '{context.reported_delay_category or 'UNREPORTED'}'."
    else:
        summary = f"Flight {context.flight_number} delay attributed to {context.deterministic_cause} ({context.deterministic_confidence} confidence)."
        explanation = (
            f"Deterministic multi-signal correlation attributed this {context.departure_delay_minutes or 0}-minute delay "
            f"to {context.deterministic_cause} based on {len(context.supporting_evidence)} corroborating evidence facts."
        )

    output = AIAnalystOutput(
        summary=summary,
        primary_cause=context.deterministic_cause,
        confidence=context.deterministic_confidence,
        explanation=explanation,
        evidence_used=context.supporting_evidence[:5],
        limitations=[
            f"Local AI analyst service unavailable ({reason}); displaying deterministic intelligence engine findings.",
        ],
    )

    return FlightAIAnalysisResponse(
        status="unavailable",
        flight_id=context.flight_id,
        flight_number=context.flight_number,
        route=context.route,
        departure_delay_minutes=context.departure_delay_minutes,
        reported_delay_category=context.reported_delay_category,
        analysis=output,
        is_grounded=True,
        model_used=None,
        execution_time_ms=0.0,
        deterministic_attribution={
            "cause": context.deterministic_cause,
            "confidence": context.deterministic_confidence,
            "score": context.deterministic_score,
            "evidence_count": len(context.supporting_evidence),
        },
    )


import threading

_CACHE_LOCK = threading.Lock()
_ANALYSIS_CACHE: Dict[int, FlightAIAnalysisResponse] = {}
_IN_PROGRESS_LOCKS: Dict[int, threading.Lock] = {}


def clear_ai_cache() -> None:
    """Clear cached AI analyses (useful for testing or manual refreshes)."""
    with _CACHE_LOCK:
        _ANALYSIS_CACHE.clear()
        _IN_PROGRESS_LOCKS.clear()


def analyze_flight_with_ai(
    conn: connection,
    flight_id: int,
    client: Optional[OllamaClient] = None,
    use_cache: bool = True,
) -> Optional[FlightAIAnalysisResponse]:
    """
    Main orchestration function for grounded AI delay analysis.
    
    1. Checks in-memory cache to return previous successful syntheses immediately.
    2. Uses per-flight concurrency locks to prevent dogpiling multiple Ollama completions.
    3. Gathers verified flight facts and deterministic intelligence from database.
    4. Constructs strict grounded prompt and calls local Ollama service.
    5. Validates JSON payload against AIAnalystOutput schema.
    6. Falls back seamlessly to deterministic findings if Ollama is unreachable.
    """
    # Bypass cache if custom/mocked client is passed (ensures test isolation)
    if client is not None:
        use_cache = False

    if use_cache:
        with _CACHE_LOCK:
            if flight_id in _ANALYSIS_CACHE and _ANALYSIS_CACHE[flight_id].status == "success":
                logger.info("Serving grounded AI analysis for flight %s from cache", flight_id)
                return _ANALYSIS_CACHE[flight_id]

        # Acquire in-progress lock for this flight to deduplicate concurrent requests
        with _CACHE_LOCK:
            if flight_id not in _IN_PROGRESS_LOCKS:
                _IN_PROGRESS_LOCKS[flight_id] = threading.Lock()
            flight_lock = _IN_PROGRESS_LOCKS[flight_id]

        flight_lock.acquire()
        try:
            # Re-check cache in case earlier request just completed
            with _CACHE_LOCK:
                if flight_id in _ANALYSIS_CACHE and _ANALYSIS_CACHE[flight_id].status == "success":
                    return _ANALYSIS_CACHE[flight_id]
            res = _execute_ai_analysis(conn, flight_id, client)
            if res and res.status == "success":
                with _CACHE_LOCK:
                    _ANALYSIS_CACHE[flight_id] = res
            return res
        finally:
            flight_lock.release()
    else:
        return _execute_ai_analysis(conn, flight_id, client)


def _execute_ai_analysis(
    conn: connection,
    flight_id: int,
    client: Optional[OllamaClient] = None,
) -> Optional[FlightAIAnalysisResponse]:
    context = assemble_grounded_context(conn, flight_id)
    if not context:
        return None

    active_client = client or ollama_client
    start_time = time.time()

    try:
        user_prompt = build_grounded_prompt(context)
        raw_completion = active_client.generate(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            format_json=True,
        )
        latency_ms = round((time.time() - start_time) * 1000, 2)

        # Parse JSON output from Ollama
        try:
            parsed_json = json.loads(raw_completion)
        except json.JSONDecodeError as json_err:
            logger.warning("Ollama returned malformed JSON: %s. Raw: %s", json_err, raw_completion[:200])
            fallback = generate_deterministic_fallback(context, reason="Malformed model JSON output")
            fallback.status = "error"
            fallback.execution_time_ms = latency_ms
            return fallback

        # Normalize and validate against Pydantic schema
        try:
            if not isinstance(parsed_json, dict):
                raise ValueError("Model output is not a JSON object")

            # Field-level fault tolerance for small/quantized models
            if "explanation" not in parsed_json or not parsed_json["explanation"]:
                parsed_json["explanation"] = parsed_json.get("details") or parsed_json.get("analysis") or parsed_json.get("summary", "Analysis details.")
            if "summary" not in parsed_json or not parsed_json["summary"]:
                parsed_json["summary"] = parsed_json["explanation"][:200]
            if "primary_cause" not in parsed_json or not parsed_json["primary_cause"]:
                parsed_json["primary_cause"] = context.deterministic_cause
            if "confidence" not in parsed_json or not parsed_json["confidence"]:
                parsed_json["confidence"] = context.deterministic_confidence

            if isinstance(parsed_json.get("evidence_used"), str):
                parsed_json["evidence_used"] = [parsed_json["evidence_used"]]
            elif not isinstance(parsed_json.get("evidence_used"), list):
                parsed_json["evidence_used"] = context.supporting_evidence[:5]

            if isinstance(parsed_json.get("limitations"), str):
                parsed_json["limitations"] = [parsed_json["limitations"]]
            elif not isinstance(parsed_json.get("limitations"), list):
                parsed_json["limitations"] = ["Standard operational logging limitations apply."]

            analysis_output = AIAnalystOutput(**parsed_json)
            
            # Enforce authoritative causal adherence: LLM cannot override primary cause or confidence
            if analysis_output.primary_cause != context.deterministic_cause:
                logger.info(
                    "Correcting LLM primary_cause from '%s' to deterministic '%s'",
                    analysis_output.primary_cause,
                    context.deterministic_cause,
                )
                analysis_output.primary_cause = context.deterministic_cause

            if analysis_output.confidence != context.deterministic_confidence:
                analysis_output.confidence = context.deterministic_confidence

        except Exception as validation_err:
            logger.warning("Pydantic validation failure on LLM response: %s", validation_err)
            fallback = generate_deterministic_fallback(context, reason="Invalid response structure from LLM")
            fallback.status = "error"
            fallback.execution_time_ms = latency_ms
            return fallback

        return FlightAIAnalysisResponse(
            status="success",
            flight_id=context.flight_id,
            flight_number=context.flight_number,
            route=context.route,
            departure_delay_minutes=context.departure_delay_minutes,
            reported_delay_category=context.reported_delay_category,
            analysis=analysis_output,
            is_grounded=True,
            model_used=active_client.model,
            execution_time_ms=latency_ms,
            deterministic_attribution={
                "cause": context.deterministic_cause,
                "confidence": context.deterministic_confidence,
                "score": context.deterministic_score,
                "evidence_count": len(context.supporting_evidence),
            },
        )

    except OllamaConnectionError as e:
        logger.info("Ollama offline; returning deterministic fallback response: %s", e)
        return generate_deterministic_fallback(context, reason="Ollama daemon unreachable")

    except OllamaTimeoutError as e:
        logger.warning("Ollama timed out; returning deterministic fallback response: %s", e)
        return generate_deterministic_fallback(context, reason="Ollama generation timeout")

    except OllamaClientError as e:
        logger.warning("Ollama client error; returning deterministic fallback response: %s", e)
        return generate_deterministic_fallback(context, reason=str(e))

    except Exception as e:
        logger.error("Unexpected error during AI analysis: %s", e, exc_info=True)
        return generate_deterministic_fallback(context, reason="Unexpected operational failure")
