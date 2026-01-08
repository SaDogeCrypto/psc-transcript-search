"""
Database connection and session management.

Provides SQLAlchemy engine, session factory, and dependency injection for FastAPI.
"""

import logging
from typing import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool, StaticPool

from src.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Determine if using SQLite
is_sqlite = settings.database_url.startswith("sqlite")

# Create engine with appropriate configuration
if is_sqlite:
    # SQLite needs special handling
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # SQLite works best with StaticPool
        echo=settings.log_level == "DEBUG",
    )
else:
    # PostgreSQL with connection pooling
    engine = create_engine(
        settings.database_url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Verify connections before use
        echo=settings.log_level == "DEBUG",
    )

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions (for scripts/background tasks).

    Usage:
        with get_db_session() as db:
            db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """
    Initialize database tables.

    Call this on application startup to ensure all tables exist.
    """
    from src.core.models.base import Base

    # Import all models so they're registered with Base
    from src.core.models import docket, document, hearing, transcript, analysis, entity

    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


# Optional: Log slow queries in development
if settings.log_level == "DEBUG":
    @event.listens_for(engine, "before_cursor_execute")
    def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(conn._execution_options.get("query_start", None))

    @event.listens_for(engine, "after_cursor_execute")
    def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        import time
        total = time.time() - (conn.info["query_start_time"].pop() or time.time())
        if total > 0.5:  # Log queries taking > 500ms
            logger.warning(f"Slow query ({total:.2f}s): {statement[:100]}...")
