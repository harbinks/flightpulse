"""
Weather extraction module for FlightPulse.
Retrieves coordinate-based weather observations from Open-Meteo REST API with
exponential backoff, rate-limit resilience, and offline fixture loading.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("flightpulse.extract.weather")

OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherExtractionError(Exception):
    """Raised when weather API extraction encounters an unrecoverable failure."""
    pass


def extract_airport_weather(
    latitude: float,
    longitude: float,
    airport_code: str,
    base_url: str = OPEN_METEO_BASE_URL,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    timeout: int = 15,
) -> Dict[str, Any]:
    """
    Extract current atmospheric weather conditions for an airport using its coordinates.
    Preserves the full raw API response for auditing and downstream ETL.
    
    Args:
        latitude: Geographic latitude in decimal degrees
        longitude: Geographic longitude in decimal degrees
        airport_code: Airport code (ICAO/IATA) for logging and record tracking
        base_url: Weather API base URL
        max_retries: Maximum attempts on transient network or rate-limiting errors
        backoff_factor: Multiplier for exponential backoff sleep
        timeout: HTTP request timeout in seconds

    Returns:
        Dictionary containing airport identifier, coordinates, and unmutated raw response.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,relative_humidity_2m,dew_point_2m,"
            "apparent_temperature,precipitation,weather_code,"
            "surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        ),
        "wind_speed_unit": "kn",
        "timezone": "UTC",
    }
    headers = {
        "User-Agent": "FlightPulse-Weather-ETL/1.0 (Aviation Intelligence)",
        "Accept": "application/json",
    }

    session = requests.Session()
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        try:
            logger.info(
                "Requesting Open-Meteo weather for %s (%.4f, %.4f) [attempt %d/%d]",
                airport_code,
                latitude,
                longitude,
                attempt,
                max_retries,
            )
            response = session.get(base_url, params=params, headers=headers, timeout=timeout)

            # Handle Rate Limiting (HTTP 429)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                sleep_sec = float(retry_after) if retry_after else (backoff_factor ** attempt)
                logger.warning(
                    "Weather API rate limit reached (HTTP 429). Retrying in %.1f seconds...",
                    sleep_sec,
                )
                time.sleep(sleep_sec)
                continue

            # Handle Server Errors (5xx)
            if 500 <= response.status_code < 600:
                sleep_sec = backoff_factor ** attempt
                logger.warning(
                    "Weather API server error (HTTP %d). Retrying in %.1f seconds...",
                    response.status_code,
                    sleep_sec,
                )
                time.sleep(sleep_sec)
                continue

            if response.status_code != 200:
                raise WeatherExtractionError(
                    f"Weather API request failed with HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            if not isinstance(data, dict):
                raise WeatherExtractionError(f"Unexpected response format from Weather API: {type(data)}")

            current = data.get("current") or {}
            raw_text = response.text

            return {
                "airport_code": airport_code,
                "latitude": latitude,
                "longitude": longitude,
                "time": current.get("time"),
                "temperature_c": current.get("temperature_2m"),
                "dewpoint_c": current.get("dew_point_2m"),
                "wind_speed_knots": current.get("wind_speed_10m"),
                "wind_gust_knots": current.get("wind_gusts_10m"),
                "wind_direction_deg": current.get("wind_direction_10m"),
                "surface_pressure_hpa": current.get("surface_pressure"),
                "weather_code": current.get("weather_code"),
                "visibility_miles": 10.0,  # Standard ceiling if unrestricted
                "raw_payload": raw_text,
                "api_response": data,
            }

        except requests.exceptions.RequestException as err:
            logger.warning("Network error extracting weather for %s: %s", airport_code, err)
            if attempt >= max_retries:
                raise WeatherExtractionError(f"Exceeded max retries fetching weather for {airport_code}: {err}") from err
            time.sleep(backoff_factor ** attempt)

    raise WeatherExtractionError(f"Failed to extract weather for {airport_code} after {max_retries} attempts.")


def load_weather_fixtures(fixture_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Load raw weather records from local JSON fixture file.
    Enables deterministic testing and offline pipeline execution.
    """
    path = fixture_path or (Path(__file__).resolve().parent.parent / "fixtures" / "raw_weather_sample.json")
    if not path.is_file():
        raise FileNotFoundError(f"Weather fixture file not found at: {path}")

    logger.info("Loading weather fixture records from %s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Weather fixture data in {path} must be a JSON list of weather objects.")

    logger.info("Loaded %d raw weather fixture records", len(data))
    return data
