"""
Shared pytest fixtures.

Points the app at a dedicated on-disk SQLite test database (isolated
from the dev mindpulse.db), wipes it clean before every test, and
provides an httpx AsyncClient wired directly to the ASGI app — no real
network socket needed (spec 2.3: pytest + httpx async test client).
"""
import os

# Must run before `backend.config`/`backend.database` are imported anywhere,
# so the app boots against the test DB and dummy VAPID keys, not real .env.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_mindpulse.db"
os.environ["VAPID_PRIVATE_KEY"] = "test-private-key"
os.environ["VAPID_PUBLIC_KEY"] = "test-public-key"
os.environ["VAPID_CLAIMS_EMAIL"] = "mailto:test@example.com"
os.environ["ALLOWED_ORIGINS"] = "http://testserver"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.database import Base, engine
from backend.main import app
from backend.services import push as push_service


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    """Fresh schema for every test — cheap enough at this scale and
    guarantees no cross-test state leaks through the singleton settings
    row or phrase/subscription tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
def _no_real_push(monkeypatch):
    """Never let a test make a real network call to a push service."""
    monkeypatch.setattr(push_service, "webpush", lambda *a, **k: None)


@pytest_asyncio.fixture(autouse=True)
async def _app_lifespan():
    """Drive the app's real startup/shutdown (same as a live server would),
    so the APScheduler instance is actually running when a test PATCHes
    /api/settings — without this, add_job()/remove_job() only queue
    "pending" changes instead of taking effect immediately."""
    async with app.router.lifespan_context(app):
        yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
