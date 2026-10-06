"""
Weather transformation and normalization module for FlightPulse.
Converts raw weather observations into normalized relational records matching
the `weather_observations` table in PostgreSQL.
"""

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("flightpulse.transform.weather")

# WMO Weather interpretation code mapping
WMO_CONDITION_MAP = {
    0: "CLEAR",
    1: "MAINLY_CLEAR",
    2: "PARTLY_CLOUDY",
    3: "OVERCAST",
    45: "FOG",
    48: "DEPOSITING_RIME_FOG",
    51: "LIGHT_DRIZZLE",
    53: "MODERATE_DRIZZLE",
    55: "DENSE_DRIZZLE",
    56: "LIGHT_FREEZING_DRIZZLE",
    57: "DENSE_FREEZING_DRIZZLE",
    61: "SLIGHT_RAIN",
    63: "MODERATE_RAIN",
    65: "HEAVY_RAIN",
    66: "LIGHT_FREEZING_RAIN",
    67: "HEAVY_FREEZING_RAIN",
    71: "SLIGHT_SNOW_FALL",
    73: "MODERATE_SNOW_FALL",
    75: "HEAVY_SNOW_FALL",
    77: "SNOW_GRAINS",
    80: "SLIGHT_RAIN_SHOWERS",
    81: "MODERATE_RAIN_SHOWERS",
    82: "VIOLENT_RAIN_SHOWERS",
    85: "SLIGHT_SNOW_SHOWERS",
    86: "HEAVY_SNOW_SHOWERS",
    95: "THUNDERSTORM",
    96: "THUNDERSTORM_WITH_SLIGHT_HAIL",
    99: "THUNDERSTORM_WITH_HEAVY_HAIL",
}


@dataclass
class TransformedWeather:
    """Normalized weather observation entity matching `weather_observations` table."""
    airport_id: int
    observation_time: datetime
    temperature_c: Optional[float]
    dewpoint_c: Optional[float]
    wind_speed_knots: Optional[float]
    wind_gust_knots: Optional[float]
    wind_direction_deg: Optional[int]
    visibility_miles: Optional[float]
    altimeter_inhg: Optional[float]
    condition_code: str
    raw_metar: str
    data_source: str
    source_record_id: str


@dataclass
class WeatherTransformReport:
    """Detailed summary of the weather transformation stage."""
    transformed: List[TransformedWeather]
    skipped_records: List[Dict[str, Any]]
    duplicate_count: int

    @property
    def total_transformed(self) -> int:
        return len(self.transformed)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped_records)


def parse_observation_timestamp(ts: Any) -> Optional[datetime]:
    """
    Parse a timestamp (Unix epoch or ISO-8601 string) into a UTC timezone-aware datetime.
    Rejects malformed, negative, or unparseable timestamps.
    """
    if ts is None or ts == "":
        return None

    # Handle numeric Unix epoch
    if isinstance(ts, (int, float)):
        try:
            val = float(ts)
            if val < 946684800 or val > 4102444800:
                return None
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return None

    # Handle string timestamp
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
            # Replace Z with +00:00 for fromisoformat compatibility
            iso_str = clean.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            pass

        # Try common datetime patterns
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(clean, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    return None


def convert_temperature_to_celsius(celsius: Any = None, fahrenheit: Any = None) -> Optional[float]:
    """Convert temperature inputs to Celsius rounded to 1 decimal place."""
    if celsius is not None:
        try:
            return round(float(celsius), 1)
        except (ValueError, TypeError):
            pass
    if fahrenheit is not None:
        try:
            return round((float(fahrenheit) - 32.0) * 5.0 / 9.0, 1)
        except (ValueError, TypeError):
            pass
    return None


def convert_wind_to_knots(
    knots: Any = None,
    mph: Any = None,
    kmh: Any = None,
) -> Optional[float]:
    """Convert wind speed inputs to knots rounded to 1 decimal place."""
    if knots is not None:
        try:
            return round(float(knots), 1)
        except (ValueError, TypeError):
            pass
    if mph is not None:
        try:
            return round(float(mph) / 1.15077945, 1)
        except (ValueError, TypeError):
            pass
    if kmh is not None:
        try:
            return round(float(kmh) / 1.852, 1)
        except (ValueError, TypeError):
            pass
    return None


def convert_pressure_to_inhg(inhg: Any = None, hpa: Any = None) -> Optional[float]:
    """Convert barometric pressure to inHg rounded to 2 decimal places."""
    if inhg is not None:
        try:
            return round(float(inhg), 2)
        except (ValueError, TypeError):
            pass
    if hpa is not None:
        try:
            return round(float(hpa) * 0.0295299830714, 2)
        except (ValueError, TypeError):
            pass
    return None


def convert_visibility_to_miles(miles: Any = None, meters: Any = None) -> Optional[float]:
    """Convert visibility inputs to statute miles rounded to 2 decimal places."""
    if miles is not None:
        try:
            return round(float(miles), 2)
        except (ValueError, TypeError):
            pass
    if meters is not None:
        try:
            return round(float(meters) / 1609.344, 2)
        except (ValueError, TypeError):
            pass
    return None


def resolve_condition_code(raw_code: Any, condition_text: Optional[str] = None) -> str:
    """Resolve WMO weather code or string condition to standard condition code."""
    if raw_code is not None:
        try:
            code_int = int(raw_code)
            if code_int in WMO_CONDITION_MAP:
                return WMO_CONDITION_MAP[code_int]
        except (ValueError, TypeError):
            pass

    if condition_text and isinstance(condition_text, str) and condition_text.strip():
        return condition_text.strip().upper().replace(" ", "_")

    return "UNKNOWN"


def match_airport(
    airport_code: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    airport_coord_map: Dict[str, Dict[str, Any]],
) -> Optional[int]:
    """
    Match an observation to an airport ID using code lookup or closest coordinates.
    """
    # 1. Match by airport code directly
    if airport_code:
        clean = airport_code.strip().upper()
        if clean in airport_coord_map:
            return airport_coord_map[clean]["id"]

    # 2. Match by coordinates (within ~30km / 0.3 degrees)
    if lat is not None and lon is not None:
        best_id = None
        min_dist = 0.35  # Max coordinate threshold in degrees
        for ap_info in airport_coord_map.values():
            d = math.hypot(ap_info["latitude"] - float(lat), ap_info["longitude"] - float(lon))
            if d < min_dist:
                min_dist = d
                best_id = ap_info["id"]
        if best_id is not None:
            return best_id

    return None


def transform_weather_records(
    raw_records: List[Dict[str, Any]],
    airport_coord_map: Dict[str, Dict[str, Any]],
    data_source: str = "OPEN_METEO",
) -> WeatherTransformReport:
    """
    Transform and validate raw weather observations against database airport mappings.
    Performs deduplication within the batch for (airport_id, observation_time).
    """
    transformed_list: List[TransformedWeather] = []
    skipped_list: List[Dict[str, Any]] = []
    seen_unique_keys: Set[Tuple[int, datetime]] = set()
    duplicate_count = 0

    for idx, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            skipped_list.append({"index": idx, "reason": "MALFORMED_RECORD_NOT_DICT"})
            continue

        # 1. Resolve Airport ID
        ap_code = raw.get("airport_code")
        lat = raw.get("latitude")
        lon = raw.get("longitude")

        airport_id = match_airport(ap_code, lat, lon, airport_coord_map)
        if not airport_id:
            skipped_list.append({
                "index": idx,
                "reason": "UNKNOWN_AIRPORT",
                "airport_code": ap_code,
                "lat": lat,
                "lon": lon,
            })
            continue

        # 2. Parse Timestamp
        time_raw = raw.get("time") or raw.get("observation_time")
        obs_time = parse_observation_timestamp(time_raw)
        if not obs_time:
            skipped_list.append({
                "index": idx,
                "reason": "INVALID_OR_MISSING_TIMESTAMP",
                "raw_time": time_raw,
            })
            continue

        # 3. Wind Direction Validation (0-360)
        wind_dir = raw.get("wind_direction_deg")
        if wind_dir is not None:
            try:
                wind_dir = int(round(float(wind_dir)))
                if not (0 <= wind_dir <= 360):
                    skipped_list.append({"index": idx, "reason": "INVALID_WIND_DIRECTION", "val": wind_dir})
                    continue
            except (ValueError, TypeError):
                wind_dir = None

        # 4. In-Batch Deduplication (airport_id, obs_time)
        unique_key = (airport_id, obs_time)
        if unique_key in seen_unique_keys:
            duplicate_count += 1
            logger.debug("Skipping in-batch duplicate weather: airport %d at %s", airport_id, obs_time)
            continue
        seen_unique_keys.add(unique_key)

        # 5. Numeric Unit Conversions
        temp_c = convert_temperature_to_celsius(raw.get("temperature_c"), raw.get("temperature_f"))
        dew_c = convert_temperature_to_celsius(raw.get("dewpoint_c"), raw.get("dewpoint_f"))
        wspd_kn = convert_wind_to_knots(raw.get("wind_speed_knots"), raw.get("wind_speed_mph"), raw.get("wind_speed_kmh"))
        wgst_kn = convert_wind_to_knots(raw.get("wind_gust_knots"), raw.get("wind_gust_mph"), raw.get("wind_gust_kmh"))
        vis_mi = convert_visibility_to_miles(raw.get("visibility_miles"), raw.get("visibility_meters"))
        altim = convert_pressure_to_inhg(raw.get("altimeter_inhg"), raw.get("surface_pressure_hpa"))
        cond_code = resolve_condition_code(raw.get("weather_code"), raw.get("condition_code"))

        # 6. Preserve Raw Payload
        raw_metar_content = raw.get("raw_payload")
        if not raw_metar_content:
            raw_metar_content = json.dumps(raw.get("api_response") or raw)

        rec_id = f"WX-{airport_id}-{int(obs_time.timestamp())}"

        transformed = TransformedWeather(
            airport_id=airport_id,
            observation_time=obs_time,
            temperature_c=temp_c,
            dewpoint_c=dew_c,
            wind_speed_knots=wspd_kn,
            wind_gust_knots=wgst_kn,
            wind_direction_deg=wind_dir,
            visibility_miles=vis_mi,
            altimeter_inhg=altim,
            condition_code=cond_code,
            raw_metar=str(raw_metar_content)[:4000],
            data_source=data_source,
            source_record_id=rec_id,
        )
        transformed_list.append(transformed)

    logger.info(
        "Weather transformation complete: %d valid records, %d skipped, %d duplicate(s) removed",
        len(transformed_list),
        len(skipped_list),
        duplicate_count,
    )
    return WeatherTransformReport(
        transformed=transformed_list,
        skipped_records=skipped_list,
        duplicate_count=duplicate_count,
    )
