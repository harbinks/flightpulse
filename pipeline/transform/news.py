"""
News and disruption transformation module for FlightPulse.
Normalizes external aviation disruption events into relational records matching
the `news_events` table in PostgreSQL.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("flightpulse.transform.news")

# Allowed event types matching `chk_news_event_type` in PostgreSQL
VALID_EVENT_TYPES = {
    "GROUND_STOP",
    "AIRPORT_OUTAGE",
    "ATC_STRIKE",
    "SEVERE_WEATHER_ALERT",
    "SECURITY_INCIDENT",
    "GENERAL_DISRUPTION",
}

# Allowed severity levels matching `chk_news_severity` in PostgreSQL
VALID_SEVERITY_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


@dataclass
class TransformedNewsEvent:
    """Normalized news/disruption record matching the `news_events` table."""
    title: str
    summary: Optional[str]
    source: str
    url: Optional[str]
    event_type: str
    severity: str
    airport_id: Optional[int]
    airline_id: Optional[int]
    start_time: datetime
    end_time: Optional[datetime]
    data_source: str
    source_record_id: str


@dataclass
class NewsTransformReport:
    """Detailed summary of the news transformation stage."""
    transformed: List[TransformedNewsEvent]
    skipped_records: List[Dict[str, Any]]
    duplicate_count: int

    @property
    def total_transformed(self) -> int:
        return len(self.transformed)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped_records)


def parse_event_timestamp(ts: Any) -> Optional[datetime]:
    """
    Parse an event timestamp string or Unix epoch into a UTC timezone-aware datetime.
    Supports ISO-8601, RFC 2822 / GMT strings (e.g. 'Mon Oct 5 12:47:44 2026 GMT'), and epoch seconds.
    """
    if ts is None or ts == "":
        return None

    # Handle numeric epoch
    if isinstance(ts, (int, float)):
        try:
            val = float(ts)
            if 946684800 <= val <= 4102444800:
                return datetime.fromtimestamp(val, tz=timezone.utc)
            return None
        except (ValueError, TypeError, OverflowError):
            return None

    if isinstance(ts, str):
        clean = ts.strip()
        # Try numeric string
        try:
            val = float(clean)
            if 946684800 <= val <= 4102444800:
                return datetime.fromtimestamp(val, tz=timezone.utc)
        except ValueError:
            pass

        # Try ISO format
        try:
            iso_str = clean.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            pass

        # Try FAA date format (e.g. "Mon Oct 5 12:47:44 2026 GMT") and common datetime formats
        formats = (
            "%a %b %d %H:%M:%S %Y GMT",
            "%a %b %d %H:%M:%S %Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(clean, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    return None


def normalize_event_type(raw_type: Optional[str], title: str = "", summary: str = "") -> str:
    """
    Normalize raw event type into allowed database categories:
    'GROUND_STOP', 'AIRPORT_OUTAGE', 'ATC_STRIKE', 'SEVERE_WEATHER_ALERT', 'SECURITY_INCIDENT', 'GENERAL_DISRUPTION'
    """
    text = f"{raw_type or ''} {title} {summary}".upper()

    if "GROUND STOP" in text or "GROUND_STOP" in text:
        return "GROUND_STOP"
    if "CLOSURE" in text or "CLOSED" in text or "OUTAGE" in text or "RUNWAY" in text:
        return "AIRPORT_OUTAGE"
    if "STRIKE" in text or "WALKOUT" in text or "INDUSTRIAL ACTION" in text:
        return "ATC_STRIKE"
    if any(k in text for k in ("THUNDERSTORM", "WIND", "SNOW", "BLIZZARD", "CONVECTIVE", "WEATHER", "HURRICANE", "FOG")):
        return "SEVERE_WEATHER_ALERT"
    if "SECURITY" in text or "TSA" in text or "EVACUATION" in text:
        return "SECURITY_INCIDENT"

    return "GENERAL_DISRUPTION"


def normalize_severity(raw_severity: Optional[str], event_type: str = "") -> str:
    """
    Normalize severity into allowed database levels: 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'.
    """
    if raw_severity and isinstance(raw_severity, str):
        clean = raw_severity.strip().upper()
        if clean in VALID_SEVERITY_LEVELS:
            return clean
        if clean in ("MODERATE", "NORMAL"):
            return "MEDIUM"
        if clean in ("SEVERE", "URGENT"):
            return "HIGH"
        if clean in ("EXTREME", "DISASTER"):
            return "CRITICAL"

    # Default based on event type
    if event_type == "GROUND_STOP":
        return "CRITICAL"
    if event_type in ("AIRPORT_OUTAGE", "SEVERE_WEATHER_ALERT", "ATC_STRIKE"):
        return "HIGH"
    return "MEDIUM"


def transform_news_records(
    raw_records: List[Dict[str, Any]],
    airport_code_map: Dict[str, int],
    airline_code_map: Dict[str, int],
    data_source: str = "FAA_ATCSCC",
) -> NewsTransformReport:
    """
    Transform and validate raw news and disruption events against database reference mappings.
    Enforces in-batch deduplication based on (source_record_id) and (title, start_time).
    """
    transformed_list: List[TransformedNewsEvent] = []
    skipped_list: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_title_times: Set[Tuple[str, datetime]] = set()
    duplicate_count = 0

    for idx, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            skipped_list.append({"index": idx, "reason": "MALFORMED_RECORD_NOT_DICT"})
            continue

        # 1. Validate Title
        title = raw.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            skipped_list.append({"index": idx, "reason": "MISSING_TITLE", "raw": raw})
            continue
        clean_title = title.strip()[:255]

        # 2. Parse Start Time (Required)
        start_time_raw = raw.get("start_time")
        start_dt = parse_event_timestamp(start_time_raw)
        if not start_dt:
            skipped_list.append({
                "index": idx,
                "reason": "INVALID_OR_MISSING_START_TIME",
                "raw_time": start_time_raw,
            })
            continue

        # 3. Parse End Time (Optional, must be >= start_time)
        end_time_raw = raw.get("end_time")
        end_dt = parse_event_timestamp(end_time_raw)
        if end_dt and end_dt < start_dt:
            # Enforce chk_news_time_window: discard invalid end time rather than rejecting event
            end_dt = None

        # 4. In-Batch Deduplication
        event_id = str(raw.get("id") or f"{clean_title}-{int(start_dt.timestamp())}")
        title_time_key = (clean_title, start_dt)

        if event_id in seen_ids or title_time_key in seen_title_times:
            duplicate_count += 1
            logger.debug("Skipping duplicate news event: %s at %s", clean_title, start_dt)
            continue
        seen_ids.add(event_id)
        seen_title_times.add(title_time_key)

        # 5. Resolve Affected Airport (Optional)
        airport_id = None
        ap_code = raw.get("airport_code")
        if ap_code and isinstance(ap_code, str):
            clean_ap = ap_code.strip().upper()
            airport_id = airport_code_map.get(clean_ap)
            if not airport_id and clean_ap.startswith("K") and len(clean_ap) == 4:
                # Try 3-letter IATA fallback for US airports (e.g. KORD -> ORD)
                airport_id = airport_code_map.get(clean_ap[1:])

        # 6. Resolve Affected Airline (Optional)
        airline_id = None
        al_code = raw.get("airline_code")
        if al_code and isinstance(al_code, str):
            clean_al = al_code.strip().upper()
            airline_id = airline_code_map.get(clean_al)

        # 7. Normalize Event Type and Severity
        summary = str(raw.get("summary") or "")
        event_type = normalize_event_type(raw.get("raw_type"), clean_title, summary)
        severity = normalize_severity(raw.get("raw_severity"), event_type)

        source_name = str(raw.get("source") or data_source)[:100]
        url = str(raw.get("url") or "") if raw.get("url") else None

        transformed = TransformedNewsEvent(
            title=clean_title,
            summary=summary[:4000] if summary else None,
            source=source_name,
            url=url,
            event_type=event_type,
            severity=severity,
            airport_id=airport_id,
            airline_id=airline_id,
            start_time=start_dt,
            end_time=end_dt,
            data_source=data_source,
            source_record_id=event_id[:100],
        )
        transformed_list.append(transformed)

    logger.info(
        "News transformation complete: %d valid records, %d skipped, %d duplicate(s) removed",
        len(transformed_list),
        len(skipped_list),
        duplicate_count,
    )
    return NewsTransformReport(
        transformed=transformed_list,
        skipped_records=skipped_list,
        duplicate_count=duplicate_count,
    )
