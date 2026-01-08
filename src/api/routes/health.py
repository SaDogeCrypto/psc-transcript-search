"""
Health check endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.api.dependencies import get_db
from src.core.config import get_settings
from src.states.registry import StateRegistry

router = APIRouter()


@router.get("/health")
def health_check():
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/health/detailed")
def detailed_health_check(db: Session = Depends(get_db)):
    """
    Detailed health check including database and configuration.
    """
    settings = get_settings()

    # Check database
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"

    # Get registered states
    states = StateRegistry.get_available_states()

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "whisper_provider": settings.whisper_provider,
        "analysis_enabled": settings.has_analysis_capability,
        "storage_type": settings.storage_type,
        "active_states": settings.active_state_list,
        "registered_states": states,
        "scrapers": StateRegistry.get_all_scrapers(),
    }


@router.get("/")
def root():
    """API root - redirects to docs."""
    return {
        "name": "PSC Hearing Intelligence API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
