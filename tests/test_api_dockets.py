"""
Test docket API endpoints.
"""

import pytest
from uuid import uuid4

from src.core.models.docket import Docket


def test_list_dockets_empty(client):
    """Test listing dockets when none exist."""
    response = client.get("/api/dockets")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_dockets_with_data(client, db_session):
    """Test listing dockets with data."""
    # Create test docket
    docket = Docket(
        state_code="FL",
        docket_number="20240001-EI",
        title="Test Rate Case",
        status="open",
        docket_type="rate_case",
    )
    db_session.add(docket)
    db_session.commit()

    response = client.get("/api/dockets")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["docket_number"] == "20240001-EI"


def test_list_dockets_filter_by_state(client, db_session):
    """Test filtering dockets by state."""
    # Create FL docket
    fl_docket = Docket(
        state_code="FL",
        docket_number="20240001-EI",
        title="Florida Docket",
    )
    db_session.add(fl_docket)
    db_session.commit()

    # Filter by FL
    response = client.get("/api/dockets?state_code=FL")
    assert response.status_code == 200
    assert response.json()["total"] == 1

    # Filter by TX (should be empty)
    response = client.get("/api/dockets?state_code=TX")
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_get_docket_not_found(client):
    """Test getting non-existent docket."""
    fake_id = str(uuid4())
    response = client.get(f"/api/dockets/{fake_id}")
    assert response.status_code == 404


def test_get_docket_by_id(client, db_session):
    """Test getting docket by ID."""
    docket = Docket(
        state_code="FL",
        docket_number="20240002-GU",
        title="Gas Utility Case",
        status="open",
    )
    db_session.add(docket)
    db_session.commit()

    response = client.get(f"/api/dockets/{docket.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["docket_number"] == "20240002-GU"
    assert data["state_code"] == "FL"
