"""
Database connection and session management using SQLAlchemy.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Support both PostgreSQL (production) and SQLite (local testing)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./data/psc_dev.db"  # Default to SQLite for local dev
)

# SQLite needs special handling
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (for SQLite development)."""
    from app.models.database import (
        State, Source, Hearing, PipelineJob, Transcript,
        Segment, Analysis, PipelineRun, AlertSubscription
    )
    Base.metadata.create_all(bind=engine)
