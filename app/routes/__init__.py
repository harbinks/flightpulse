"""
Export API routers.
"""

from app.routes.disruptions import router as disruptions_router
from app.routes.flights import router as flights_router
from app.routes.health import router as health_router
from app.routes.intelligence import router as intelligence_router
from app.routes.timeline import router as timeline_router
from app.routes.weather import router as weather_router

__all__ = [
    "health_router",
    "flights_router",
    "weather_router",
    "disruptions_router",
    "intelligence_router",
    "timeline_router",
]
