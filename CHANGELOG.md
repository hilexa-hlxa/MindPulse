# Changelog

All notable changes to this project are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Structured JSON logging** (`structlog`) — every log line, ours and
  uvicorn/apscheduler's, is one JSON object with a `request_id` merged in
  automatically for the duration of a request (`RequestIDMiddleware`),
  echoed back as an `X-Request-ID` response header. Notification cycles
  log a structured `notification_sent`/`notification_skipped` event with
  phrase ID, subscriber count, and delivered/expired/failed counts.
- **Rate limiting** (`slowapi`) — `POST /api/phrases` capped at
  20/minute, `POST /api/settings/trigger` at 5/minute, per client IP.
  Exceeding a limit returns `429`.
- **Push delivery retries** — transient failures (anything except a
  410/404 Gone response) now retry up to 3 times with exponential
  backoff (1s, 2s) before giving up, off the event loop
  (`asyncio.to_thread`) so one slow subscriber can't stall the request
  handling every other client. A 410/404 still short-circuits
  immediately — retrying a dead subscription just wastes time.
- **`delivery_log` table** — one row per (notification cycle,
  subscription) attempt: status (`delivered`/`expired`/`failed`),
  attempt count, and the last error message. Feeds the new stats
  endpoint's "sent today" counter.
- **`GET /api/stats`** — total/active phrase counts, active subscriber
  count, notifications delivered today, and the most-sent phrase.
  Surfaced on the Dashboard.
- **Phrase categories/tags** — many-to-many `Phrase <-> Category`, plus
  a second many-to-many from the settings singleton to `Category` used
  as an optional send filter ("only send phrases tagged X"). New
  `GET /api/categories`; `POST`/`PATCH /api/phrases` accept a
  `categories` list (get-or-create by name, normalized to
  trimmed+lowercased); `PATCH /api/settings` accepts `category_filter`.
  `GET /api/phrases/random` and the scheduler now share one
  `pick_random_active_phrase()` query so the Dashboard's preview always
  matches what would actually be sent. Frontend: tag input on Add,
  chips on the Phrases list, filter checkboxes on Settings.
- **Real Playwright E2E test** (`backend/tests/test_e2e.py`) — boots the
  app as a live subprocess, drives real Chromium: adds a phrase through
  the actual Add form, confirms the exact text renders in the Phrases
  list, fires "Send now", confirms the Dashboard's last-sent timestamp
  advances. Marked `e2e`, excluded from the default `pytest` run
  (needs `playwright install chromium`), runs as a separate CI step.
- **OpenAPI polish** — summary/description/response docs on every
  endpoint, tag descriptions, request/response examples on schemas.
  Swagger UI screenshot added to the README.
- **Bruno API collection** (`bruno/`) — every endpoint as a `.bru`
  request, a `Local` environment; verified by actually running the
  whole collection against a live server (`npx @usebruno/cli run`),
  not just hand-written and assumed correct.
- `CHANGELOG.md` (this file).

### Fixed
- `PATCH /api/settings` with `category_filter` was silently ignored in
  the *response* (though correctly persisted to the DB) — the
  `SettingsOut` schema's field name didn't match the ORM relationship
  name (`category_filter` vs. `active_categories`), so Pydantic's
  `from_attributes` conversion found nothing and fell back to an empty
  list. Fixed with an explicit `validation_alias`.
- **Postgres-only crash**: the category-filtered random-phrase query
  used `SELECT DISTINCT ... ORDER BY random()`, which SQLite silently
  allows but Postgres correctly rejects (`InvalidColumnReferenceError`:
  `random()` isn't in the select list). Every SQLite-backed test passed;
  it only surfaced running the real `docker-compose` Postgres stack,
  which is exactly why that stack gets exercised for real rather than
  just written and assumed to work. Fixed by confining the `DISTINCT`
  to an id-only subquery with no `ORDER BY`, so the outer query's
  `ORDER BY random()` never conflicts with it.
- Switching back to the Dashboard tab never refreshed its data (stale
  interval/last-sent/stats) — `showView()` only refreshed the Phrases
  and Settings tabs, not Dashboard.
- Phrase `text`/`author` weren't trimmed; a blank author (`"   "`)
  stored as an empty string instead of `null`.

### Changed
- `services/push.py`: `send_to_all()` now takes a `phrase_id` (for the
  delivery log FK) and returns `delivered`/`expired`/`failed` counts
  instead of a `sent` count — the old key name collided with the
  cycle-level `sent: bool` in the caller's merged response dict.

## [1.0.1] — Hardening pass

_Commit `8a07f89`, following the initial build in `89bf99f`._

### Added
- `Dockerfile` + `docker-compose.yml` (app + real Postgres 16) — built
  and smoke-tested live: `alembic upgrade head` running
  `PostgresqlImpl` migrations, a phrase created over the API and
  confirmed via `psql` directly against the container.
- GitHub Actions CI (`ruff check` + `pytest`) on every push/PR.
- `ruff` configuration; fixed all findings it turned up (datetime.UTC
  alias, import ordering, one unused import). FastAPI's idiomatic
  `Depends(...)`-as-default pattern allowlisted rather than "fixed"
  into something broken.
- Real PWA install UX: `beforeinstallprompt` captured for a working
  Install button (confirmed firing against Chrome's actual
  installability audit), a manual "Add to Home Screen" hint for iOS
  Safari (which never fires that event), Apple PWA meta tags.
- `backend/scripts/seed_demo_phrases.py`, MIT `LICENSE`.
- 9 new tests (health/vapid endpoints, DB URL rewriting, phrase
  text/author normalization) — 38 passing, up from 29.

### Fixed
- Phrase/author fields weren't trimmed; blank author stored as `""`
  instead of `null`.

## [1.0.0] — Initial build

_Commit `89bf99f`._

FastAPI + APScheduler backend, Web Push notifications via `pywebpush`,
SQLAlchemy 2.0 async models, Alembic migrations, vanilla-JS PWA
frontend (4 views, service worker, manifest, generated icons), 29
passing pytest tests, Render/Railway deploy configs — the full tech
spec's Definition of Done except live deployment (needs the owner's
hosting account).
