"""Tests for GET /api/stats (spec round 3, item 4)."""


async def test_stats_on_empty_db(client):
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "total_phrases": 0,
        "active_phrases": 0,
        "total_subscribers": 0,
        "notifications_sent_today": 0,
        "most_sent_phrase": None,
    }


async def test_stats_counts_phrases_and_subscribers(client):
    p1 = (await client.post("/api/phrases", json={"text": "Active one"})).json()
    p2 = (await client.post("/api/phrases", json={"text": "Inactive one"})).json()
    await client.patch(f"/api/phrases/{p2['id']}", json={"is_active": False})

    await client.post(
        "/api/subscriptions",
        json={"endpoint": "https://push.example.com/a", "keys": {"p256dh": "k", "auth": "a"}},
    )

    resp = await client.get("/api/stats")
    body = resp.json()
    assert body["total_phrases"] == 2
    assert body["active_phrases"] == 1
    assert body["total_subscribers"] == 1
    assert p1["id"]  # sanity: fixture created successfully


async def test_stats_notifications_sent_today_and_most_sent_phrase(client):
    await client.post("/api/phrases", json={"text": "Winner", "author": "Champ"})
    await client.post(
        "/api/subscriptions",
        json={"endpoint": "https://push.example.com/b", "keys": {"p256dh": "k", "auth": "a"}},
    )

    for _ in range(3):
        resp = await client.post("/api/settings/trigger")
        assert resp.status_code == 200

    resp = await client.get("/api/stats")
    body = resp.json()
    assert body["notifications_sent_today"] == 3
    assert body["most_sent_phrase"]["text"] == "Winner"
    assert body["most_sent_phrase"]["times_sent"] == 3
