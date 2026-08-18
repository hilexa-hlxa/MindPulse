"""Tests for /api/subscriptions (spec 5.2)."""

SUB_PAYLOAD = {
    "endpoint": "https://push.example.com/sub/abc123",
    "keys": {"p256dh": "fake-p256dh-key", "auth": "fake-auth-secret"},
}


async def test_create_subscription_returns_201(client):
    resp = await client.post("/api/subscriptions", json=SUB_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["endpoint"] == SUB_PAYLOAD["endpoint"]
    assert body["is_active"] is True


async def test_create_subscription_rejects_missing_keys(client):
    resp = await client.post("/api/subscriptions", json={"endpoint": "https://push.example.com/x"})
    assert resp.status_code == 422


async def test_resubscribing_same_endpoint_reactivates_instead_of_conflicting(client):
    first = await client.post("/api/subscriptions", json=SUB_PAYLOAD)
    assert first.status_code == 201
    first_id = first.json()["id"]

    updated_payload = {**SUB_PAYLOAD, "keys": {"p256dh": "new-key", "auth": "new-auth"}}
    second = await client.post("/api/subscriptions", json=updated_payload)
    assert second.status_code == 201
    assert second.json()["id"] == first_id  # same row, not a duplicate


async def test_delete_subscription_returns_204(client):
    await client.post("/api/subscriptions", json=SUB_PAYLOAD)
    resp = await client.request("DELETE", "/api/subscriptions", json={"endpoint": SUB_PAYLOAD["endpoint"]})
    assert resp.status_code == 204


async def test_delete_unknown_subscription_is_still_204(client):
    """Unsubscribing something that was never subscribed reaches the same
    end state the client wants, so it's a no-op success, not an error."""
    resp = await client.request("DELETE", "/api/subscriptions", json={"endpoint": "https://nope.example.com"})
    assert resp.status_code == 204
