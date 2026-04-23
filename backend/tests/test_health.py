from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_health_check_healthy():
    with patch("main.check_db_connection", new_callable=AsyncMock, return_value=True):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_health_check_degraded():
    with patch("main.check_db_connection", new_callable=AsyncMock, return_value=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "disconnected"
