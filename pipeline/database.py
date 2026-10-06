"""
Database connection and lookup utilities for FlightPulse pipeline.
Provides connection management and foreign-key lookup caches for airports and airlines.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, Tuple
import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import RealDictCursor

from pipeline.config import config

logger = logging.getLogger("flightpulse.database")


def get_db_connection() -> connection:
    """Create and return a new PostgreSQL connection."""
    db = config.database
    try:
        conn = psycopg2.connect(
            host=db.host,
            port=db.port,
            dbname=db.name,
            user=db.user,
            password=db.password,
            connect_timeout=10,
        )
        return conn
    except Exception as exc:
        logger.error("Failed to connect to PostgreSQL database %s on %s:%s: %s", db.name, db.host, db.port, exc)
        raise


@contextmanager
def get_db_cursor(commit: bool = True):
    """Context manager for database cursor operations."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_airport_lookup(conn: connection) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Load airport code mappings from PostgreSQL.
    Returns:
        tuple of (icao_to_id, iata_to_id)
    """
    icao_map: Dict[str, int] = {}
    iata_map: Dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, iata_code, icao_code FROM airports;")
        rows = cur.fetchall()
        for airport_id, iata, icao in rows:
            if iata:
                iata_map[iata.strip().upper()] = airport_id
            if icao:
                icao_map[icao.strip().upper()] = airport_id
    logger.debug("Loaded %d ICAO and %d IATA airport lookups", len(icao_map), len(iata_map))
    return icao_map, iata_map


def load_airline_lookup(conn: connection) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Load airline code mappings from PostgreSQL.
    Returns:
        tuple of (icao_to_id, iata_to_id)
    """
    icao_map: Dict[str, int] = {}
    iata_map: Dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, iata_code, icao_code FROM airlines WHERE active = TRUE;")
        rows = cur.fetchall()
        for airline_id, iata, icao in rows:
            if iata:
                iata_map[iata.strip().upper()] = airline_id
            if icao:
                icao_map[icao.strip().upper()] = airline_id
    logger.debug("Loaded %d ICAO and %d IATA airline lookups", len(icao_map), len(iata_map))
    return icao_map, iata_map


def load_airports_with_coordinates(conn: connection) -> Dict[str, Dict[str, Any]]:
    """
    Load all airports with latitude, longitude, and elevation from PostgreSQL.
    Returns:
        Dictionary keyed by uppercase ICAO and IATA codes pointing to airport metadata dict.
    """
    airports: Dict[str, Dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, iata_code, icao_code, name, latitude, longitude, elevation_ft, timezone FROM airports;")
        rows = cur.fetchall()
        for row in rows:
            airport_id, iata, icao, name, lat, lon, elev, tz = row
            info = {
                "id": airport_id,
                "iata_code": iata.strip().upper() if iata else None,
                "icao_code": icao.strip().upper() if icao else None,
                "name": name,
                "latitude": float(lat),
                "longitude": float(lon),
                "elevation_ft": elev,
                "timezone": tz,
            }
            if icao:
                airports[icao.strip().upper()] = info
            if iata:
                airports[iata.strip().upper()] = info
    logger.debug("Loaded %d airport coordinate references", len(airports))
    return airports

