"""
Test health check endpoints.
"""

import pytest


def test_health_check(client):
    """Test basic health check."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root(client):
    """Test API root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


def test_detailed_health(client):
    """Test detailed health check."""
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert "database" in data
    assert "whisper_provider" in data
    assert "registered_states" in data
