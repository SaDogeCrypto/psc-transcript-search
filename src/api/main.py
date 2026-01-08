"""
FastAPI application factory.

Creates and configures the FastAPI app with:
- CORS middleware
- Route registration
- Exception handlers
- Startup/shutdown events
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.database import init_db

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting PSC Hearing Intelligence API")
    logger.info(f"Active states: {settings.active_state_list}")
    logger.info(f"Whisper provider: {settings.whisper_provider}")

    # Initialize database tables
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database init warning: {e}")

    yield

    # Shutdown
    logger.info("Shutting down API")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(
        title="PSC Hearing Intelligence API",
        description="API for Public Service Commission hearing transcripts and analysis",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://*.azurestaticapps.net",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    from src.api.routes import dockets, documents, hearings, search, health, states, stats
    from src.api.routes.admin import pipeline, scrapers

    # Public routes
    app.include_router(health.router, tags=["health"])
    app.include_router(states.router, prefix="/api/states", tags=["states"])
    app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
    app.include_router(dockets.router, prefix="/api/dockets", tags=["dockets"])
    app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
    app.include_router(hearings.router, prefix="/api/hearings", tags=["hearings"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])

    # Admin routes (mapped to /admin/* for backward compatibility)
    app.include_router(pipeline.router, prefix="/api/admin/pipeline", tags=["admin"])
    app.include_router(pipeline.router, prefix="/admin/pipeline", tags=["admin"])
    app.include_router(scrapers.router, prefix="/api/admin/scrapers", tags=["admin"])
    app.include_router(scrapers.router, prefix="/admin/scrapers", tags=["admin"])
    app.include_router(stats.router, prefix="/admin/stats", tags=["admin"])
    app.include_router(states.router, prefix="/admin/states", tags=["admin"])

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

    return app


# Create default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
