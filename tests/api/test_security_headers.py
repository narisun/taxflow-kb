"""Tests for security headers middleware."""
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app


@pytest.fixture
async def raw_client():
    """Minimal client — no DB, just checks middleware on the health endpoint."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_security_headers_present(raw_client):
    resp = await raw_client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "max-age=" in resp.headers["strict-transport-security"]
    assert resp.headers["x-xss-protection"] == "0"
    assert "default-src" in resp.headers["content-security-policy"]
