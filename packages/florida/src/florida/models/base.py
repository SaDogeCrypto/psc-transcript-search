"""
Base SQLAlchemy configuration for Florida models.
"""
import os
from sqlalchemy import create_engine, JSON
from sqlalchemy.orm import sessionmaker, declarative_base

# Florida-specific database URL
FL_DATABASE_URL = os.getenv(
    "FL_DATABASE_URL",
    os.getenv("DATABASE_URL", "postgresql://localhost/psc_florida")
)

# Determine if using SQLite
IS_SQLITE = FL_DATABASE_URL.startswith("sqlite")

# Create engine
if IS_SQLITE:
    engine = create_engine(
        FL_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(FL_DATABASE_URL, pool_pre_ping=True)

# Database-compatible JSON type
# Use JSON for SQLite, JSONB for PostgreSQL
if IS_SQLITE:
    JSONB = JSON  # Alias for SQLite compatibility
    # For ARRAY, use JSON to store as serialized list in SQLite
    def ARRAY(item_type):
        return JSON
else:
    from sqlalchemy.dialects.postgresql import JSONB, ARRAY

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all Florida models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (for development)."""
    from florida.models.docket import FLDocket
    from florida.models.document import FLDocument
    from florida.models.hearing import FLHearing, FLTranscriptSegment
    from florida.models.entity import FLEntity
    from florida.models.analysis import FLAnalysis
    Base.metadata.create_all(bind=engine)
