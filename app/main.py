"""
CanaryScope API - Main Application

Production FastAPI backend for the CanaryScope utility regulatory intelligence platform.
Provides both public API endpoints and admin dashboard endpoints.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine, SessionLocal
from app.api.routes import admin, public
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup: verify database connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database connection verified")
    except Exception as e:
        print(f"Warning: Database connection failed: {e}")

    yield

    # Shutdown: cleanup
    engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="CanaryScope API",
    description="""
    API for the CanaryScope utility regulatory intelligence platform.

    ## Features

    - **States**: Browse states with PSC hearing data
    - **Hearings**: Search and filter hearings by state, date, utility, and type
    - **Dockets**: Track regulatory dockets and proceedings
    - **Watchlist**: Manage watched dockets with email notifications
    - **Transcripts**: Access full transcripts with speaker identification
    - **Search**: Full-text and semantic search across all transcripts
    - **Analysis**: AI-generated insights including summaries, key issues, and predictions

    ## Admin Endpoints

    Admin endpoints under `/admin` provide pipeline monitoring, source management,
    and system statistics for internal use.
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
# In production, restrict origins to your frontend domains
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (configurable via RATE_LIMIT_PER_MINUTE env var)
rate_limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
app.add_middleware(RateLimitMiddleware, requests_per_minute=rate_limit)

# Include routers
app.include_router(public.router)
app.include_router(admin.router)


@app.get("/")
def root():
    """API root endpoint."""
    return {
        "name": "CanaryScope API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "healthy"
    }


@app.get("/debug")
def debug_info():
    """Debug endpoint to check configuration."""
    import os
    from app.database import DATABASE_URL
    return {
        "database_url_set": bool(os.getenv("DATABASE_URL")),
        "database_url_prefix": DATABASE_URL[:30] + "..." if len(DATABASE_URL) > 30 else DATABASE_URL,
        "is_postgresql": DATABASE_URL.startswith("postgresql")
    }


@app.get("/health")
def health_check():
    """Health check endpoint for load balancers."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENV", "development") == "development"
    )
