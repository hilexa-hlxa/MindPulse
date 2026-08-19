"""Tests for slowapi rate limits (spec round 3, item 2)."""


async def test_create_phrase_is_rate_limited_at_20_per_minute(client):
    for i in range(20):
        resp = await client.post("/api/phrases", json={"text": f"Phrase {i}"})
        assert resp.status_code == 201, f"request {i} should still be within budget"

    resp = await client.post("/api/phrases", json={"text": "One too many"})
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"].lower()


async def test_trigger_is_rate_limited_at_15_per_minute(client):
    await client.post("/api/phrases", json={"text": "Some phrase"})

    for i in range(15):
        resp = await client.post("/api/settings/trigger")
        assert resp.status_code == 200, f"trigger {i} should still be within budget"

    resp = await client.post("/api/settings/trigger")
    assert resp.status_code == 429


async def test_other_endpoints_are_not_rate_limited_by_the_phrase_limit(client):
    """GET /api/phrases has no limiter applied — only creation is throttled."""
    for _ in range(25):
        resp = await client.get("/api/phrases")
        assert resp.status_code == 200
