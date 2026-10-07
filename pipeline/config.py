"""
Configuration module for FlightPulse data ingestion pipeline.
Loads database and API settings from environment variables.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _normalize_database_url(raw_url: str) -> str:
    """Safely ensure the password component of DATABASE_URL is percent-encoded."""
    if not raw_url:
        return ""
    try:
        from urllib.parse import quote, unquote
        if "://" in raw_url and "@" in raw_url:
            scheme, remainder = raw_url.split("://", 1)
            creds, host_and_rest = remainder.split("@", 1)
            if ":" in creds:
                user, password = creds.split(":", 1)
                # Unquote in case partly encoded, then fully quote special chars
                encoded_password = quote(unquote(password), safe="")
                return f"{scheme}://{user}:{encoded_password}@{host_and_rest}"
    except Exception:
        pass
    return raw_url


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = _normalize_database_url(os.getenv("DATABASE_URL", ""))
    host: str = os.getenv("DB_HOST", os.getenv("DATABASE_HOST", "localhost"))
    port: int = int(os.getenv("DB_PORT", os.getenv("DATABASE_PORT", "5432")))
    name: str = os.getenv("DB_NAME", os.getenv("DATABASE_NAME", "flightpulse"))
    user: str = os.getenv("DB_USER", os.getenv("DATABASE_USER", "postgres"))
    password: str = os.getenv("DB_PASSWORD", os.getenv("DATABASE_PASSWORD", ""))


@dataclass(frozen=True)
class OpenSkyConfig:
    username: str = os.getenv("OPENSKY_USERNAME", "")
    password: str = os.getenv("OPENSKY_PASSWORD", "")
    base_url: str = os.getenv("OPENSKY_BASE_URL", "https://opensky-network.org/api")
    request_timeout: int = int(os.getenv("OPENSKY_TIMEOUT_SEC", "20"))
    max_retries: int = int(os.getenv("OPENSKY_MAX_RETRIES", "3"))
    backoff_factor: float = float(os.getenv("OPENSKY_BACKOFF_FACTOR", "2.0"))


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "llama3:latest")
    timeout_sec: float = float(os.getenv("OLLAMA_TIMEOUT_SEC", "180.0"))


@dataclass(frozen=True)
class PipelineConfig:
    data_source: str = os.getenv("FLIGHT_DATA_SOURCE", "fixture").lower()
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    default_airports: tuple = ("KATL", "KORD", "KDFW", "KDEN", "KJFK", "KLAX", "KSFO", "EGLL")
    database: DatabaseConfig = DatabaseConfig()
    opensky: OpenSkyConfig = OpenSkyConfig()
    ollama: OllamaConfig = OllamaConfig()


# Global config instance
config = PipelineConfig()
