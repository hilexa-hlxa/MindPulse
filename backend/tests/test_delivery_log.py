"""Tests for retry-with-backoff and delivery_log recording (spec round 3, item 3)."""
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.delivery_log import DeliveryLog
from backend.models.subscription import PushSubscription
from backend.services import push as push_service
from backend.services.scheduler import send_random_notification


async def test_transient_failure_retries_then_succeeds(client, monkeypatch):
    await client.post("/api/phrases", json={"text": "Retry me"})
    await client.post(
        "/api/subscriptions",
        json={"endpoint": "https://push.example.com/flaky", "keys": {"p256dh": "k", "auth": "a"}},
    )

    calls = {"n": 0}

    def flaky_webpush(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("simulated network blip")
        return None  # succeeds on the 2nd attempt

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(push_service, "webpush", flaky_webpush)
    monkeypatch.setattr(push_service, "_sleep", fake_sleep)

    result = await send_random_notification()
    assert result["delivered"] == 1
    assert calls["n"] == 2
    assert sleeps == [1]  # one backoff wait before the successful 2nd attempt

    async with AsyncSessionLocal() as db:
        log = (await db.execute(select(DeliveryLog))).scalar_one()
        assert log.status == "delivered"
        assert log.attempts == 2
        assert log.error is None


async def test_persistent_failure_exhausts_retries_and_logs_failed(client, monkeypatch):
    await client.post("/api/phrases", json={"text": "Always fails"})
    await client.post(
        "/api/subscriptions",
        json={"endpoint": "https://push.example.com/dead", "keys": {"p256dh": "k", "auth": "a"}},
    )

    def always_fails(*args, **kwargs):
        raise TimeoutError("simulated persistent failure")

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(push_service, "webpush", always_fails)
    monkeypatch.setattr(push_service, "_sleep", fake_sleep)

    result = await send_random_notification()
    assert result["failed"] == 1
    assert result["delivered"] == 0

    async with AsyncSessionLocal() as db:
        log = (await db.execute(select(DeliveryLog))).scalar_one()
        assert log.status == "failed"
        assert log.attempts == 3  # exhausted MAX_ATTEMPTS
        assert "TimeoutError" in log.error

    # Generic failures are transient by assumption — only a 410/404 Gone
    # response should ever deactivate a subscription.
    async with AsyncSessionLocal() as db:
        sub = (await db.execute(select(PushSubscription))).scalar_one()
        assert sub.is_active is True


async def test_expired_subscription_skips_retries(client, monkeypatch):
    """410 Gone should short-circuit immediately, not burn all 3 attempts."""
    from pywebpush import WebPushException

    await client.post("/api/phrases", json={"text": "Gone"})
    await client.post(
        "/api/subscriptions",
        json={"endpoint": "https://push.example.com/expired", "keys": {"p256dh": "k", "auth": "a"}},
    )

    class FakeResponse:
        status_code = 410

    calls = {"n": 0}

    def gone(*args, **kwargs):
        calls["n"] += 1
        raise WebPushException("gone", response=FakeResponse())

    monkeypatch.setattr(push_service, "webpush", gone)

    result = await send_random_notification()
    assert result["expired"] == 1
    assert calls["n"] == 1  # no retries for a definitive 410

    async with AsyncSessionLocal() as db:
        log = (await db.execute(select(DeliveryLog))).scalar_one()
        assert log.status == "expired"
        assert log.attempts == 1
