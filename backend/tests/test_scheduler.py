"""Tests for the notification delivery job itself (spec 6.2)."""
import pytest
from pywebpush import WebPushException

from backend.database import AsyncSessionLocal
from backend.models.phrase import Phrase
from backend.models.subscription import PushSubscription
from backend.services import push as push_service
from backend.services.scheduler import send_random_notification
from backend.services.settings_repo import get_or_create_settings


async def test_send_random_notification_no_active_phrases_is_a_noop():
    result = await send_random_notification()
    assert result == {"sent": False, "reason": "no active phrases"}


async def test_send_random_notification_increments_times_sent_and_last_sent(client):
    created = await client.post("/api/phrases", json={"text": "Grow daily", "author": None})
    phrase_id = created.json()["id"]

    result = await send_random_notification()
    assert result["sent"] is True
    assert result["phrase_id"] == phrase_id

    async with AsyncSessionLocal() as db:
        phrase = await db.get(Phrase, phrase_id)
        assert phrase.times_sent == 1

        app_settings = await get_or_create_settings(db)
        assert app_settings.last_sent_at is not None


async def test_send_random_notification_skips_inactive_phrases(client):
    resp = await client.post("/api/phrases", json={"text": "Never sent", "author": None})
    phrase_id = resp.json()["id"]
    await client.patch(f"/api/phrases/{phrase_id}", json={"is_active": False})

    result = await send_random_notification()
    assert result == {"sent": False, "reason": "no active phrases"}


async def test_send_random_notification_deactivates_expired_subscription(client, monkeypatch):
    await client.post("/api/phrases", json={"text": "Ping", "author": None})
    await client.post(
        "/api/subscriptions",
        json={"endpoint": "https://push.example.com/gone", "keys": {"p256dh": "k", "auth": "a"}},
    )

    class FakeResponse:
        status_code = 410

    def fake_webpush(*args, **kwargs):
        raise WebPushException("gone", response=FakeResponse())

    monkeypatch.setattr(push_service, "webpush", fake_webpush)

    result = await send_random_notification()
    assert result["expired"] == 1
    assert result["delivered"] == 0

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        row = (await db.execute(select(PushSubscription))).scalar_one()
        assert row.is_active is False


async def test_send_random_notification_counts_successful_delivery(client):
    await client.post("/api/phrases", json={"text": "Delivered", "author": None})
    await client.post(
        "/api/subscriptions",
        json={"endpoint": "https://push.example.com/ok", "keys": {"p256dh": "k", "auth": "a"}},
    )

    # conftest's autouse _no_real_push fixture makes webpush() a no-op success.
    result = await send_random_notification()
    assert result["delivered"] == 1
    assert result["expired"] == 0
