"""
Test hearing API endpoints.
"""

import pytest
from datetime import date
from uuid import uuid4

from src.core.models.hearing import Hearing


def test_list_hearings_empty(client):
    """Test listing hearings when none exist."""
    response = client.get("/api/hearings")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_hearings_with_data(client, db_session):
    """Test listing hearings with data."""
    hearing = Hearing(
        state_code="FL",
        docket_number="20240001-EI",
        title="Rate Case Hearing",
        hearing_type="evidentiary",
        hearing_date=date(2024, 6, 15),
        transcript_status="pending",
    )
    db_session.add(hearing)
    db_session.commit()

    response = client.get("/api/hearings")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Rate Case Hearing"


def test_list_hearings_filter_by_status(client, db_session):
    """Test filtering hearings by transcript status."""
    # Create hearings with different statuses
    pending = Hearing(
        state_code="FL",
        title="Pending Hearing",
        transcript_status="pending",
    )
    transcribed = Hearing(
        state_code="FL",
        title="Transcribed Hearing",
        transcript_status="transcribed",
    )
    db_session.add_all([pending, transcribed])
    db_session.commit()

    # Filter by pending
    response = client.get("/api/hearings?status=pending")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "Pending Hearing"

    # Filter by transcribed
    response = client.get("/api/hearings?status=transcribed")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_get_hearing_not_found(client):
    """Test getting non-existent hearing."""
    fake_id = str(uuid4())
    response = client.get(f"/api/hearings/{fake_id}")
    assert response.status_code == 404


def test_get_hearing_by_id(client, db_session):
    """Test getting hearing by ID with full details."""
    hearing = Hearing(
        state_code="FL",
        docket_number="20240003-WU",
        title="Water Utility Hearing",
        hearing_type="public_hearing",
        hearing_date=date(2024, 7, 20),
        full_text="This is the transcript text.",
        word_count=5,
        transcript_status="transcribed",
    )
    db_session.add(hearing)
    db_session.commit()

    response = client.get(f"/api/hearings/{hearing.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Water Utility Hearing"
    assert data["full_text"] == "This is the transcript text."
    assert data["transcript_status"] == "transcribed"


def test_get_hearing_statuses(client, db_session):
    """Test getting hearing status counts."""
    # Create hearings with different statuses
    for status in ["pending", "pending", "transcribed", "analyzed"]:
        hearing = Hearing(state_code="FL", transcript_status=status)
        db_session.add(hearing)
    db_session.commit()

    response = client.get("/api/hearings/statuses")
    assert response.status_code == 200
    data = response.json()

    status_counts = {item["status"]: item["count"] for item in data}
    assert status_counts.get("pending") == 2
    assert status_counts.get("transcribed") == 1
    assert status_counts.get("analyzed") == 1
