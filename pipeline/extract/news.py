"""
News and disruption event extraction module for FlightPulse.
Extracts real aviation disruption events from the FAA Air Traffic Control System
Command Center (ATCSCC) NAS Status API and provides offline fixture loading.
"""

import json
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("flightpulse.extract.news")

FAA_NAS_STATUS_URL = "https://nasstatus.faa.gov/api/airport-status-information"


class NewsExtractionError(Exception):
    """Raised when news/event extraction encounters an unrecoverable failure."""
    pass


def extract_faa_nas_events(
    url: str = FAA_NAS_STATUS_URL,
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """
    Extract live airport disruption events from FAA ATCSCC NAS status XML feed.
    Preserves raw source payloads and attribution metadata.
    
    Args:
        url: FAA ATCSCC API endpoint URL
        max_retries: Maximum attempts on transient network errors
        backoff_factor: Multiplier for exponential backoff sleep
        timeout: HTTP request timeout in seconds

    Returns:
        List of unmutated raw disruption event dictionaries.
    """
    headers = {
        "User-Agent": "FlightPulse-Intelligence/1.0 (Aviation Delay Research)",
        "Accept": "application/xml, text/xml, */*",
    }

    session = requests.Session()
    attempt = 0

    while attempt < max_retries:
        attempt += 1
        try:
            logger.info("Requesting FAA NAS status advisories from %s [attempt %d/%d]", url, attempt, max_retries)
            response = session.get(url, headers=headers, timeout=timeout)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                sleep_sec = float(retry_after) if retry_after else (backoff_factor ** attempt)
                logger.warning("FAA API rate limit (HTTP 429). Retrying in %.1f seconds...", sleep_sec)
                time.sleep(sleep_sec)
                continue

            if 500 <= response.status_code < 600:
                sleep_sec = backoff_factor ** attempt
                logger.warning("FAA server error (HTTP %d). Retrying in %.1f seconds...", response.status_code, sleep_sec)
                time.sleep(sleep_sec)
                continue

            if response.status_code != 200:
                raise NewsExtractionError(
                    f"FAA NAS status request failed with HTTP {response.status_code}: {response.text[:200]}"
                )

            raw_xml = response.text
            try:
                root = ET.fromstring(response.content)
            except ET.ParseError as err:
                raise NewsExtractionError(f"Failed to parse FAA NAS status XML: {err}") from err

            update_time = root.findtext("Update_Time") or ""
            events: List[Dict[str, Any]] = []

            for delay_type in root.findall("Delay_type"):
                category_name = delay_type.findtext("Name") or "General Disruption"
                for list_container in delay_type:
                    if list_container.tag == "Name":
                        continue
                    for item in list_container:
                        arpt = item.findtext("ARPT") or ""
                        reason = item.findtext("Reason") or "Air traffic flow management advisory"
                        avg_delay = item.findtext("Avg") or ""
                        max_delay = item.findtext("Max") or ""
                        end_time = item.findtext("End_Time") or None

                        summary_parts = [reason]
                        if avg_delay:
                            summary_parts.append(f"Average delay: {avg_delay}")
                        if max_delay:
                            summary_parts.append(f"Maximum delay: {max_delay}")
                        summary = ". ".join(summary_parts)

                        event_id = f"FAA-{arpt.strip()}-{category_name.replace(' ', '_')}-{int(time.time())}"
                        title = f"FAA {category_name}: {arpt.strip()} ({reason[:60]})" if arpt else f"FAA {category_name}: {reason[:60]}"

                        events.append({
                            "id": event_id,
                            "title": title[:255],
                            "summary": summary,
                            "source": "FAA ATCSCC",
                            "url": url,
                            "raw_type": category_name,
                            "raw_severity": "High" if "Stop" in category_name or "Closure" in category_name else "Medium",
                            "airport_code": arpt.strip() if arpt else None,
                            "airline_code": None,
                            "start_time": update_time,
                            "end_time": end_time,
                            "raw_payload": ET.tostring(item, encoding="unicode"),
                        })

            logger.info("Successfully extracted %d FAA disruption events from live feed", len(events))
            return events

        except requests.exceptions.RequestException as err:
            logger.warning("Network error extracting FAA NAS status: %s", err)
            if attempt >= max_retries:
                raise NewsExtractionError(f"Exceeded max retries fetching FAA status: {err}") from err
            time.sleep(backoff_factor ** attempt)

    raise NewsExtractionError(f"Failed to extract FAA NAS events after {max_retries} attempts.")


def load_news_fixtures(fixture_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Load raw disruption events from local JSON fixture file.
    Enables deterministic testing and offline pipeline execution.
    """
    path = fixture_path or (Path(__file__).resolve().parent.parent / "fixtures" / "raw_news_sample.json")
    if not path.is_file():
        raise FileNotFoundError(f"News fixture file not found at: {path}")

    logger.info("Loading news fixture records from %s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"News fixture data in {path} must be a JSON array of event objects.")

    logger.info("Loaded %d raw news fixture records", len(data))
    return data
