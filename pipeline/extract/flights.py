"""
Flight extraction module for FlightPulse.
Handles extraction from OpenSky Network REST API with retry / exponential backoff
and local fixture loading for deterministic testing.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from requests.auth import HTTPBasicAuth

from pipeline.config import config

logger = logging.getLogger("flightpulse.extract")


class OpenSkyExtractionError(Exception):
    """Custom exception raised when OpenSky API extraction fails."""
    pass


def extract_opensky_flights(
    airport_icao: str,
    begin_timestamp: int,
    end_timestamp: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    base_url: Optional[str] = None,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    timeout: int = 20,
) -> List[Dict[str, Any]]:
    """
    Extract flight departures from the OpenSky Network REST API.
    
    Args:
        airport_icao: 4-character ICAO airport code (e.g. 'KORD')
        begin_timestamp: Unix epoch timestamp in seconds
        end_timestamp: Unix epoch timestamp in seconds (max interval 2 hours per OpenSky docs)
        username: Optional OpenSky username
        password: Optional OpenSky password
        base_url: API base URL override
        max_retries: Maximum number of retries upon rate limit or transient error
        backoff_factor: Multiplier for exponential backoff sleep
        timeout: HTTP request timeout in seconds

    Returns:
        List of raw flight dictionaries returned by OpenSky API.
    """
    url = f"{base_url or config.opensky.base_url}/flights/departure"
    params = {
        "airport": airport_icao.strip().upper(),
        "begin": int(begin_timestamp),
        "end": int(end_timestamp),
    }

    auth = None
    user = username or config.opensky.username
    pwd = password or config.opensky.password
    if user and pwd:
        auth = HTTPBasicAuth(user, pwd)
        logger.debug("Using authenticated OpenSky request for user: %s", user)
    else:
        logger.debug("Using anonymous OpenSky request (rate limits apply)")

    headers = {
        "User-Agent": "FlightPulse-Pipeline/1.0 (Aviation Intelligence Research)",
        "Accept": "application/json",
    }

    session = requests.Session()
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        try:
            logger.info(
                "Requesting OpenSky departures for %s (attempt %d/%d, window: %s to %s)",
                airport_icao,
                attempt,
                max_retries,
                begin_timestamp,
                end_timestamp,
            )
            response = session.get(url, params=params, auth=auth, headers=headers, timeout=timeout)

            # Handle Rate Limiting (HTTP 429)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                sleep_sec = float(retry_after) if retry_after else (backoff_factor ** attempt)
                logger.warning(
                    "OpenSky rate limit encountered (HTTP 429). Retrying in %.1f seconds...",
                    sleep_sec,
                )
                time.sleep(sleep_sec)
                continue

            # Handle Server Errors (5xx) with backoff
            if 500 <= response.status_code < 600:
                sleep_sec = backoff_factor ** attempt
                logger.warning(
                    "OpenSky server error (HTTP %d). Retrying in %.1f seconds...",
                    response.status_code,
                    sleep_sec,
                )
                time.sleep(sleep_sec)
                continue

            # Client error or unexpected status
            if response.status_code != 200:
                raise OpenSkyExtractionError(
                    f"OpenSky request failed with HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            if not isinstance(data, list):
                logger.warning("OpenSky returned unexpected response format (not a list): %s", type(data))
                return []

            logger.info("Successfully extracted %d flight records from OpenSky for %s", len(data), airport_icao)
            return data

        except requests.exceptions.RequestException as err:
            logger.warning("Network request error during OpenSky extraction: %s", err)
            if attempt >= max_retries:
                raise OpenSkyExtractionError(f"Exceeded max retries ({max_retries}) connecting to OpenSky: {err}") from err
            time.sleep(backoff_factor ** attempt)

    raise OpenSkyExtractionError(f"Failed to extract OpenSky flights after {max_retries} attempts.")


def load_fixture_flights(fixture_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Load raw flight records from local JSON fixture file.
    Enables deterministic offline testing and CI/CD validation.
    """
    path = fixture_path or (Path(__file__).resolve().parent.parent / "fixtures" / "raw_flights_sample.json")
    if not path.is_file():
        raise FileNotFoundError(f"Flight fixture file not found at: {path}")

    logger.info("Loading flight fixture records from %s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Fixture data in {path} must be a JSON array of flight objects.")

    logger.info("Loaded %d raw fixture flight records", len(data))
    return data
