"""
FlightPulse Intelligence API Main Application.
Production-style FastAPI backend exposing deterministic flight delay intelligence,
weather observations, FAA disruption notices, and chronological timelines.
"""

import logging
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.ai import router as ai_router
from app.routes.disruptions import router as disruptions_router
from app.routes.flights import router as flights_router
from app.routes.health import router as health_router
from app.routes.intelligence import router as intelligence_router
from app.routes.timeline import router as timeline_router
from app.routes.weather import router as weather_router
from pipeline.config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

app = FastAPI(
    title="FlightPulse Intelligence API",
    description="End-to-End Flight Delay Intelligence & Operational Disruption Attribution Platform",
    version="1.0.0",
)

# Configure CORS for local development (React/Vite on 5173, Streamlit on 8501)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from pathlib import Path
from fastapi.staticfiles import StaticFiles

# Register route modules
app.include_router(health_router)
app.include_router(flights_router)
app.include_router(weather_router)
app.include_router(disruptions_router)
app.include_router(intelligence_router)
app.include_router(timeline_router)
app.include_router(ai_router)

from fastapi import Request
from fastapi.responses import JSONResponse
import psycopg2

@app.exception_handler(psycopg2.Error)
async def postgresql_exception_handler(request: Request, exc: psycopg2.Error):
    logging.getLogger("flightpulse.api").error("Database error processing request %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Operational database service temporarily unavailable. Please retry shortly."},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logging.getLogger("flightpulse.api").error("Unhandled exception processing request %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal operational error occurred processing the flight request."},
    )

# Mount built React/Vite dashboard if available
dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dist_dir), html=True), name="dashboard")


import threading


def _prewarm_ai_cache() -> None:
    """Pre-warm in-memory AI analyst cache for primary demo flight in background thread."""
    try:
        from pipeline.database import get_db_connection
        from app.services.ai_analyst import analyze_flight_with_ai
        conn = get_db_connection()
        try:
            analyze_flight_with_ai(conn, flight_id=2)
            logging.getLogger("flightpulse.ai").info("Background pre-warm for flight 2 complete.")
        finally:
            conn.close()
    except Exception as e:
        logging.getLogger("flightpulse.ai").debug("Background pre-warm notice: %s", e)


@app.on_event("startup")
def on_startup() -> None:
    threading.Thread(target=_prewarm_ai_cache, daemon=True).start()


@app.get("/", tags=["Root"])
def root():
    """API root descriptor."""
    return {
        "platform": "FlightPulse",
        "description": "Deterministic flight delay intelligence platform",
        "dashboard": "/dashboard",
        "documentation": "/docs",
        "health": "/health",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
