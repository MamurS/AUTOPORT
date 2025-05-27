# tests/test_simple.py
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from main import app

def test_health_check_sync():
    """Test health check endpoint using sync client."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

def test_api_root_sync():
    """Test API root endpoint using sync client."""
    with TestClient(app) as client:
        response = client.get("/api/v1")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "status" in data
        assert data["status"] == "healthy"

@pytest.mark.asyncio
async def test_health_check_async():
    """Test health check endpoint using async client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}