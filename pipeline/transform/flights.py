"""
Flight transformation and validation module for FlightPulse.
Converts raw flight objects into normalized relational entities adhering to the PostgreSQL schema.
Handles deduplication, missing fields, timestamp parsing, delay computation, and unknown foreign keys.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("flightpulse.transform")

# Regex to parse flight callsigns: e.g. DAL1042 -> DAL + 1042, DL1042 -> DL + 1042
CALLSIGN_PATTERN = re.compile(r"^([A-Za-z]{2,3})(\d+[A-Za-z]?)$")


@dataclass
class TransformedFlight:
    """Normalized flight entity matching the PostgreSQL `flights` table."""
    flight_number: str
    airline_id: int
    origin_airport_id: int
    destination_airport_id: int
    flight_date: str  # YYYY-MM-DD
    scheduled_departure: Optional[datetime]
    actual_departure: Optional[datetime]
    scheduled_arrival: Optional[datetime]
    actual_arrival: Optional[datetime]
    status: str
    departure_delay_minutes: Optional[int]
    arrival_delay_minutes: Optional[int]
    delay_category: Optional[str]
    tail_number: Optional[str]
    aircraft_type: Optional[str]
    distance_miles: Optional[float]
    data_source: str
    source_record_id: str


@dataclass
class TransformReport:
    """Detailed summary of the transformation process."""
    transformed: List[TransformedFlight]
    skipped_records: List[Dict[str, Any]]
    duplicate_count: int

    @property
    def total_transformed(self) -> int:
        return len(self.transformed)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped_records)


def parse_unix_timestamp(ts: Any) -> Optional[datetime]:
    """
    Safely parse a Unix epoch timestamp (seconds) into a UTC timezone-aware datetime.
    Rejects negative, non-numeric, or absurd timestamps (before 2000 or after 2100).
    """
    if ts is None or ts == "":
        return None
    try:
        val = float(ts)
        # Check realistic timestamp bounds (2000-01-01 to 2100-01-01)
        if val < 946684800 or val > 4102444800:
            logger.debug("Rejected out-of-bounds timestamp: %s", ts)
            return None
        return datetime.fromtimestamp(val, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        logger.debug("Failed to parse timestamp value: %s", ts)
        return None


def parse_callsign(callsign: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse an ICAO/IATA callsign into carrier prefix and flight number.
    e.g. 'DAL1042' -> ('DAL', 'DL1042'), 'SWA1892' -> ('SWA', 'WN1892')
    """
    if not callsign or not isinstance(callsign, str):
        return None, None
    clean = callsign.strip().upper()
    match = CALLSIGN_PATTERN.match(clean)
    if match:
        carrier_code, number = match.groups()
        return carrier_code, f"{carrier_code}{number}"
    return None, None


def compute_delay_minutes(scheduled: Optional[datetime], actual: Optional[datetime]) -> int:
    """
    Compute delay in integer minutes between scheduled and actual times.
    Positive value indicates late; negative indicates early.
    """
    if scheduled is None or actual is None:
        return 0
    diff_sec = (actual - scheduled).total_seconds()
    return int(round(diff_sec / 60.0))


def transform_flight_records(
    raw_records: List[Dict[str, Any]],
    airport_icao_map: Dict[str, int],
    airport_iata_map: Dict[str, int],
    airline_icao_map: Dict[str, int],
    airline_iata_map: Dict[str, int],
    data_source: str = "OPENSKY",
) -> TransformReport:
    """
    Transform and validate raw flight records against database lookups.
    Performs deduplication within the batch, keeping the most complete record.
    """
    transformed_list: List[TransformedFlight] = []
    skipped_list: List[Dict[str, Any]] = []
    seen_unique_keys: Set[Tuple[int, str, datetime]] = set()
    duplicate_count = 0

    for idx, raw in enumerate(raw_records):
        # 1. Validate required fields presence
        callsign_raw = raw.get("callsign")
        if not callsign_raw:
            skipped_list.append({"index": idx, "reason": "MISSING_CALLSIGN", "raw": raw})
            continue

        carrier_code, parsed_flight_num = parse_callsign(callsign_raw)
        if not carrier_code or not parsed_flight_num:
            skipped_list.append({"index": idx, "reason": "INVALID_CALLSIGN_FORMAT", "raw": raw})
            continue

        # 2. Resolve Airline
        airline_id = airline_icao_map.get(carrier_code) or airline_iata_map.get(carrier_code)
        if not airline_id:
            skipped_list.append({
                "index": idx,
                "reason": "UNKNOWN_AIRLINE",
                "carrier": carrier_code,
                "callsign": callsign_raw,
            })
            continue

        # 3. Resolve Origin and Destination Airports
        origin_code = (raw.get("estDepartureAirport") or raw.get("departureAirport") or "").strip().upper()
        dest_code = (raw.get("estArrivalAirport") or raw.get("arrivalAirport") or "").strip().upper()

        if not origin_code or not dest_code:
            skipped_list.append({"index": idx, "reason": "MISSING_AIRPORT_CODES", "raw": raw})
            continue

        if origin_code == dest_code:
            skipped_list.append({"index": idx, "reason": "IDENTICAL_ORIGIN_DESTINATION", "raw": raw})
            continue

        origin_id = airport_icao_map.get(origin_code) or airport_iata_map.get(origin_code)
        dest_id = airport_icao_map.get(dest_code) or airport_iata_map.get(dest_code)

        if not origin_id:
            skipped_list.append({"index": idx, "reason": "UNKNOWN_ORIGIN_AIRPORT", "code": origin_code})
            continue
        if not dest_id:
            skipped_list.append({"index": idx, "reason": "UNKNOWN_DESTINATION_AIRPORT", "code": dest_code})
            continue

        # 4. Parse Timestamps
        # OpenSky provides firstSeen (actual dep) and lastSeen (actual arr).
        raw_sched_dep = raw.get("scheduledDeparture")
        raw_sched_arr = raw.get("scheduledArrival")
        has_published_schedule = bool(raw_sched_dep)

        is_cancelled = bool(raw.get("isCancelled") or raw.get("status") == "CANCELLED")

        actual_dep = parse_unix_timestamp(raw.get("firstSeen") or raw.get("actualDeparture"))
        actual_arr = parse_unix_timestamp(raw.get("lastSeen") or raw.get("actualArrival"))

        if has_published_schedule:
            sched_dep = parse_unix_timestamp(raw_sched_dep)
            if not sched_dep:
                skipped_list.append({"index": idx, "reason": "INVALID_SCHEDULED_DEPARTURE_TIMESTAMP", "raw": raw})
                continue
            sched_arr = parse_unix_timestamp(raw_sched_arr) if raw_sched_arr else sched_dep
        else:
            # Telemetry-only live observation: OpenSky does NOT provide commercial timetables.
            # Represent unknown values honestly: NULL for all commercial schedule and delay attributes.
            sched_dep = None
            sched_arr = None

        # Rejection check: must have at least one valid departure timestamp (scheduled or actual)
        ref_timestamp = sched_dep or actual_dep
        if not ref_timestamp:
            skipped_list.append({"index": idx, "reason": "MISSING_DEPARTURE_TIMESTAMPS", "raw": raw})
            continue

        # 5. Classify Status & Delays
        if is_cancelled:
            status = "CANCELLED"
            dep_delay = 0
            arr_delay = 0
            actual_dep = None
            actual_arr = None
        elif has_published_schedule:
            dep_delay = compute_delay_minutes(sched_dep, actual_dep)
            arr_delay = compute_delay_minutes(sched_arr, actual_arr)
            if actual_arr is not None:
                status = "LANDED"
            elif actual_dep is not None:
                status = "EN_ROUTE"
            else:
                status = "SCHEDULED"
        else:
            # Telemetry-only live observation: delay is unknown and must NOT be fabricated as 0
            dep_delay = None
            arr_delay = None
            if actual_arr is not None:
                status = "LANDED"
            elif actual_dep is not None:
                status = "EN_ROUTE"
            else:
                status = "ACTIVE"

        # 6. Delay Category (Source-reported - only valid if explicitly provided by source)
        if has_published_schedule:
            delay_cat = raw.get("delayCategory")
            if delay_cat and delay_cat.upper() in {"CARRIER", "WEATHER", "NAS", "SECURITY", "LATE_AIRCRAFT", "OTHER"}:
                delay_cat = delay_cat.upper()
            else:
                delay_cat = None
        else:
            # Never invent or assign a delay category for raw telemetry observations
            delay_cat = None

        # 7. Check In-Batch Deduplication
        # For live telemetry observations, key by (airline_id, icao24, actual_dep)
        icao24 = (raw.get("icao24") or "").strip().lower()
        if not has_published_schedule and icao24:
            unique_key = (airline_id, icao24, actual_dep)
        else:
            unique_key = (airline_id, parsed_flight_num, sched_dep)

        if unique_key in seen_unique_keys:
            duplicate_count += 1
            logger.debug("Skipping in-batch duplicate flight: %s at %s", parsed_flight_num, ref_timestamp)
            continue
        seen_unique_keys.add(unique_key)

        flight_date = ref_timestamp.strftime("%Y-%m-%d")
        source_rec_id = str(icao24 or raw.get("source_record_id") or f"{parsed_flight_num}-{int(ref_timestamp.timestamp())}")

        transformed = TransformedFlight(
            flight_number=parsed_flight_num,
            airline_id=airline_id,
            origin_airport_id=origin_id,
            destination_airport_id=dest_id,
            flight_date=flight_date,
            scheduled_departure=sched_dep,
            actual_departure=actual_dep,
            scheduled_arrival=sched_arr,
            actual_arrival=actual_arr,
            status=status,
            departure_delay_minutes=dep_delay,
            arrival_delay_minutes=arr_delay,
            delay_category=delay_cat,
            tail_number=icao24 or None,
            aircraft_type=raw.get("aircraftType"),
            distance_miles=float(raw.get("distanceMiles")) if raw.get("distanceMiles") else None,
            data_source=data_source,
            source_record_id=source_rec_id,
        )
        transformed_list.append(transformed)

    logger.info(
        "Transformation complete: %d valid records, %d skipped, %d in-batch duplicates removed",
        len(transformed_list),
        len(skipped_list),
        duplicate_count,
    )
    return TransformReport(
        transformed=transformed_list,
        skipped_records=skipped_list,
        duplicate_count=duplicate_count,
    )
