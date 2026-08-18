"""Tests for meta endpoints and config helpers not covered elsewhere."""
from backend.config import Settings


async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_vapid_public_key_endpoint_exposes_configured_key(client):
    resp = await client.get("/api/vapid-public-key")
    assert resp.status_code == 200
    assert resp.json() == {"publicKey": "test-public-key"}


def test_async_database_url_rewrites_plain_postgres_scheme():
    settings = Settings(database_url="postgres://user:pw@host:5432/db")
    assert settings.async_database_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_async_database_url_rewrites_postgresql_scheme():
    settings = Settings(database_url="postgresql://user:pw@host:5432/db")
    assert settings.async_database_url == "postgresql+asyncpg://user:pw@host:5432/db"


def test_async_database_url_leaves_sqlite_untouched():
    settings = Settings(database_url="sqlite+aiosqlite:///./mindpulse.db")
    assert settings.async_database_url == "sqlite+aiosqlite:///./mindpulse.db"


def test_cors_origins_splits_and_strips():
    settings = Settings(allowed_origins="http://a.com, http://b.com ,,http://c.com")
    assert settings.cors_origins == ["http://a.com", "http://b.com", "http://c.com"]
