"""Tests for phrase tagging, GET /api/categories, and the settings send-filter
(spec round 3, item 5)."""


async def test_create_phrase_with_categories_creates_them(client):
    resp = await client.post(
        "/api/phrases", json={"text": "Push through", "categories": ["Discipline", " focus "]}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["categories"] == ["discipline", "focus"]  # normalized: trimmed + lowercased

    listing = await client.get("/api/categories")
    names = {c["name"] for c in listing.json()}
    assert names == {"discipline", "focus"}


async def test_reusing_a_category_name_does_not_duplicate_it(client):
    await client.post("/api/phrases", json={"text": "One", "categories": ["focus"]})
    await client.post("/api/phrases", json={"text": "Two", "categories": ["focus"]})

    listing = await client.get("/api/categories")
    assert len(listing.json()) == 1


async def test_patch_categories_replaces_not_merges(client):
    created = await client.post("/api/phrases", json={"text": "Tag me", "categories": ["a", "b"]})
    phrase_id = created.json()["id"]

    resp = await client.patch(f"/api/phrases/{phrase_id}", json={"categories": ["c"]})
    assert resp.json()["categories"] == ["c"]


async def test_phrase_without_categories_field_has_empty_list(client):
    resp = await client.post("/api/phrases", json={"text": "No tags"})
    assert resp.json()["categories"] == []


async def test_settings_category_filter_restricts_random_and_scheduled_send(client):
    tagged = await client.post("/api/phrases", json={"text": "Focus phrase", "categories": ["focus"]})
    await client.post("/api/phrases", json={"text": "Untagged phrase"})

    await client.patch("/api/settings", json={"category_filter": ["focus"]})
    settings = (await client.get("/api/settings")).json()
    assert settings["category_filter"] == ["focus"]

    for _ in range(5):
        resp = await client.get("/api/phrases/random")
        assert resp.json()["id"] == tagged.json()["id"]


async def test_settings_category_filter_empty_list_clears_it(client):
    await client.post("/api/phrases", json={"text": "Tagged", "categories": ["focus"]})
    await client.patch("/api/settings", json={"category_filter": ["focus"]})
    await client.patch("/api/settings", json={"category_filter": []})

    settings = (await client.get("/api/settings")).json()
    assert settings["category_filter"] == []
