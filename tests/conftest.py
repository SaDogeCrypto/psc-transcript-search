"""
Pytest configuration and fixtures.
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Set test environment - use in-memory SQLite for tests
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["STORAGE_TYPE"] = "local"
os.environ["AUDIO_DIR"] = "./test_audio"

from src.core.models.base import Base
from src.core.database import get_db
from src.api.main import create_app

# Import all models to register them with Base.metadata
from src.core.models.docket import Docket
from src.core.models.document import Document
from src.core.models.hearing import Hearing
from src.core.models.transcript import TranscriptSegment
from src.core.models.analysis import Analysis
from src.core.models.entity import Entity

# Also import Florida models
from src.states.florida.models.docket import FLDocketDetails
from src.states.florida.models.document import FLDocumentDetails
from src.states.florida.models.hearing import FLHearingDetails

# Test database setup - synchronous SQLite for tests
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine."""
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    # Clean up test database file
    if os.path.exists("./test.db"):
        os.remove("./test.db")


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a new database session for each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create test client with database override."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    """Headers for admin API authentication."""
    return {"X-API-Key": "test-admin-key"}
