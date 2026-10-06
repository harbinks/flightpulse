"""
Database session and connection dependency for FastAPI app.
Provides connection pooling and lifecycle management.
"""

from typing import Generator
import psycopg2
from psycopg2.extensions import connection
from psycopg2.extras import RealDictCursor

from pipeline.database import get_db_connection


def get_db() -> Generator[connection, None, None]:
    """FastAPI dependency yielding an open PostgreSQL database connection."""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
