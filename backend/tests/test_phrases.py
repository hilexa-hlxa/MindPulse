"""CRUD + validation tests for /api/phrases (spec 5.1)."""
import pytest


async def _create(client, text="Ship it.", author="Test"):
    resp = await client.post("/api/phrases", json={"text": text, "author": author})
    assert resp.status_code == 201
    return resp.json()


async def test_create_phrase_returns_201_and_payload(client):
    body = await _create(client, "Make it first, make it great later.", "Unknown")
    assert body["text"] == "Make it first, make it great later."
    assert body["author"] == "Unknown"
    assert body["is_active"] is True
    assert body["times_sent"] == 0
    assert "id" in body and "created_at" in body


async def test_create_phrase_without_author_is_optional(client):
    body = await _create(client, "Keep going.", author=None)
    assert body["author"] is None


async def test_create_phrase_rejects_empty_text(client):
    resp = await client.post("/api/phrases", json={"text": ""})
    assert resp.status_code == 422


async def test_create_phrase_requires_text_field(client):
    resp = await client.post("/api/phrases", json={"author": "Nobody"})
    assert resp.status_code == 422


async def test_list_phrases_returns_active_and_inactive(client):
    p1 = await _create(client, "Active one")
    p2 = await _create(client, "Inactive one")
    await client.patch(f"/api/phrases/{p2['id']}", json={"is_active": False})

    resp = await client.get("/api/phrases")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {p1["id"], p2["id"]} <= ids


async def test_random_phrase_only_returns_active(client):
    active = await _create(client, "I'm active")
    inactive = await _create(client, "I'm not")
    await client.patch(f"/api/phrases/{inactive['id']}", json={"is_active": False})

    for _ in range(5):
        resp = await client.get("/api/phrases/random")
        assert resp.status_code == 200
        assert resp.json()["id"] == active["id"]


async def test_random_phrase_404_when_none_active(client):
    resp = await client.get("/api/phrases/random")
    assert resp.status_code == 404


async def test_patch_phrase_updates_text_author_and_active(client):
    phrase = await _create(client, "Original text", "Original author")

    resp = await client.patch(
        f"/api/phrases/{phrase['id']}",
        json={"text": "Updated text", "author": "Updated author", "is_active": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Updated text"
    assert body["author"] == "Updated author"
    assert body["is_active"] is False


async def test_patch_phrase_partial_update_leaves_other_fields(client):
    phrase = await _create(client, "Keep this text", "Keep this author")
    resp = await client.patch(f"/api/phrases/{phrase['id']}", json={"is_active": False})
    body = resp.json()
    assert body["text"] == "Keep this text"
    assert body["author"] == "Keep this author"
    assert body["is_active"] is False


async def test_patch_nonexistent_phrase_returns_404(client):
    resp = await client.patch("/api/phrases/999999", json={"is_active": False})
    assert resp.status_code == 404


async def test_delete_phrase_returns_204_and_removes_it(client):
    phrase = await _create(client)
    resp = await client.delete(f"/api/phrases/{phrase['id']}")
    assert resp.status_code == 204

    listing = await client.get("/api/phrases")
    assert phrase["id"] not in {p["id"] for p in listing.json()}


async def test_delete_nonexistent_phrase_returns_404(client):
    resp = await client.delete("/api/phrases/999999")
    assert resp.status_code == 404
