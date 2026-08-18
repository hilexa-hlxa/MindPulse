"""Tests for /api/settings (spec 5.3) and live scheduler rescheduling (US-06/08)."""
from backend.services import scheduler as scheduler_service


async def test_get_settings_returns_defaults(client):
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval_minutes"] == 60
    assert body["is_running"] is True
    assert body["last_sent_at"] is None


async def test_patch_settings_updates_interval(client):
    resp = await client.patch("/api/settings", json={"interval_minutes": 30})
    assert resp.status_code == 200
    assert resp.json()["interval_minutes"] == 30


async def test_patch_settings_rejects_interval_below_minimum(client):
    resp = await client.patch("/api/settings", json={"interval_minutes": 5})
    assert resp.status_code == 422


async def test_patch_settings_rejects_interval_above_maximum(client):
    resp = await client.patch("/api/settings", json={"interval_minutes": 500})
    assert resp.status_code == 422


async def test_patch_settings_updates_scheduler_job_interval_live(client):
    """US-06: interval changes apply to the live APScheduler job without a restart."""
    await client.patch("/api/settings", json={"interval_minutes": 45})
    job = scheduler_service.scheduler.get_job(scheduler_service.JOB_ID)
    assert job is not None
    assert job.trigger.interval.total_seconds() == 45 * 60


async def test_patch_settings_pause_removes_scheduler_job(client):
    """US-08: pausing stops the scheduler; resuming restarts it."""
    await client.patch("/api/settings", json={"is_running": False})
    assert scheduler_service.scheduler.get_job(scheduler_service.JOB_ID) is None

    resp = await client.patch("/api/settings", json={"is_running": True})
    assert resp.json()["is_running"] is True
    assert scheduler_service.scheduler.get_job(scheduler_service.JOB_ID) is not None


async def test_trigger_endpoint_fires_immediately_regardless_of_schedule(client):
    """US-07."""
    await client.post("/api/phrases", json={"text": "Fire now", "author": None})
    resp = await client.post("/api/settings/trigger")
    assert resp.status_code == 200
    assert resp.json()["sent"] is True
