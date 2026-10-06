"""
Health check route.
"""

from typing import Dict
from fastapi import APIRouter, Depends
from psycopg2.extensions import connection

from app.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(conn: connection = Depends(get_db)) -> Dict[str, str]:
    """Verify application and PostgreSQL database health."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1;")
        cur.fetchone()
    return {
        "status": "healthy",
        "database": "connected",
        "platform": "FlightPulse Intelligence API",
    }
