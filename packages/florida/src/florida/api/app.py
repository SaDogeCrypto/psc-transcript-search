"""
Florida PSC FastAPI application.

Provides REST API for Florida regulatory intelligence:
- /api/fl/dockets - Docket listing and search
- /api/fl/documents - Document search
- /api/fl/hearings - Hearing transcripts
- /api/fl/pipeline - Pipeline status and execution
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from florida.api.routes import dockets, documents, hearings, search, dashboard, admin, review
from florida.config import get_config


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()

    app = FastAPI(
        title="Florida PSC API",
        description="Florida Public Service Commission regulatory intelligence API",
        version="0.1.0",
        docs_url="/api/fl/docs",
        redoc_url="/api/fl/redoc",
        openapi_url="/api/fl/openapi.json",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(dockets.router, prefix="/api/fl")
    app.include_router(documents.router, prefix="/api/fl")
    app.include_router(hearings.router, prefix="/api/fl")
    app.include_router(search.router, prefix="/api/fl")

    # Dashboard-compatible routes (mounted at /api for customer dashboard)
    app.include_router(dashboard.router)

    # Admin routes for pipeline management
    app.include_router(admin.router)

    # Review routes for entity linking
    app.include_router(review.router)

    @app.get("/api/fl/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "florida-psc"}

    @app.get("/api/fl/status")
    async def get_status():
        """Get API and database status."""
        from florida.models import get_db
        from florida.pipeline import FloridaPipelineOrchestrator

        try:
            db = next(get_db())
            orchestrator = FloridaPipelineOrchestrator(db)
            status = orchestrator.get_pipeline_status()
            db.close()
            return {
                "status": "healthy",
                "database": "connected",
                "pipeline": status,
            }
        except Exception as e:
            return {
                "status": "degraded",
                "database": "error",
                "error": str(e),
            }

    return app


# Default app instance
app = create_app()


def main():
    """Run the development server."""
    import uvicorn
    uvicorn.run(
        "florida.api.app:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )


if __name__ == "__main__":
    main()
