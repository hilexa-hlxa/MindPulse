# MindPulse

[![CI](https://github.com/hilexa-hlxa/MindPulse/actions/workflows/ci.yml/badge.svg)](https://github.com/hilexa-hlxa/MindPulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Scheduled motivational push notifications, delivered like a native app.

MindPulse is a Progressive Web App: install it to your phone's home screen and
it pushes a short, user-curated phrase to you on a configurable interval — a
FastAPI + APScheduler backend driving the Web Push API, with a vanilla
HTML/CSS/JS frontend (no framework, by design). Built as a portfolio project
demonstrating fullstack Python, background scheduling, PWA setup, and clean
REST API design.

![Dashboard](docs/screenshot-dashboard.jpg)
![Phrases list](docs/screenshot-phrases.jpg)

## Features

- 🔔 One-tap "Enable Notifications" — permission is only ever requested on an
  explicit tap, never on page load
- ⏱️ Configurable delivery interval (15 min – 4 h), reschedules live, no
  server restart needed
- ✍️ Add, edit, toggle, and delete your own motivational phrases
- 🚀 Manual "send now" trigger, independent of the schedule
- ⏸️ Pause/resume the whole scheduler with one switch
- 📱 Installable PWA: manifest + service worker, works offline for the app
  shell, receives push while the browser is closed
- 📲 Real install prompt on Chrome/Edge/Android (captured `beforeinstallprompt`,
  verified firing against Chrome's actual installability audit) plus a manual
  "Add to Home Screen" hint for iOS Safari, which never fires that event
- 🧪 38 passing pytest tests covering CRUD, validation, scheduler, and push logic
- 🐳 Dockerfile + docker-compose (with a real Postgres service) for a
  production-like local run
- ✅ CI on every push/PR: ruff lint + full pytest suite

## Architecture

```
Browser (PWA)  ←→  FastAPI Server  ←→  SQLite / Postgres
                        │
                        ▼
              APScheduler (background, in-process)
                        │
                        ▼
         pywebpush → Push Service → Service Worker → Notification
```

- **Backend** — FastAPI + SQLAlchemy 2.0 (async) + Alembic migrations.
  `AsyncIOScheduler` runs on the same event loop as the API, so its job body
  can `await` DB queries and push sends directly.
- **Frontend** — a single HTML page with four views (Dashboard, Phrases, Add,
  Settings) swapped by a tiny vanilla-JS router; no build step.
- **Push** — the browser's own Push API + a service worker (`sw.js`); the
  backend never talks to the browser directly, only to the browser vendor's
  push service, authenticated with a VAPID key pair.

## Tech Stack

| Layer | Choice |
|---|---|
| API framework | FastAPI |
| Background scheduling | APScheduler (`AsyncIOScheduler`) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Database | SQLite (dev) / Postgres (production) |
| Push | pywebpush + VAPID |
| Frontend | HTML5 / CSS3 / vanilla JS, Service Worker API, Web App Manifest |
| Tests | pytest + pytest-asyncio + httpx `ASGITransport` |
| Deploy | Render.com or Railway (free tier) |

## Project Layout

```
mindpulse/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py                # Settings, VAPID keys, env vars
│   ├── database.py              # SQLAlchemy async engine + session
│   ├── models/                  # Phrase, PushSubscription, AppSettings
│   ├── schemas/                 # Pydantic request/response models
│   ├── routers/                 # phrases, subscriptions, settings
│   ├── services/                # scheduler.py, push.py, settings_repo.py
│   ├── scripts/                 # generate_vapid_keys.py, generate_icons.py, seed_demo_phrases.py
│   ├── alembic/                 # DB migrations
│   └── tests/                   # pytest suite (38 tests)
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── sw.js                    # Service Worker
│   ├── manifest.json
│   └── icons/
├── .github/workflows/ci.yml     # lint + test on every push/PR
├── .env.example
├── requirements.txt
├── pyproject.toml                # ruff config
├── Dockerfile
├── docker-compose.yml            # app + real Postgres, for local/demo use
├── Procfile                      # Railway / generic
└── render.yaml                   # Render.com blueprint
```

## Setup

### 1. Clone and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Generate a VAPID key pair

Web Push requires a VAPID key pair for authenticating notifications:

```bash
python backend/scripts/generate_vapid_keys.py
```

Copy the printed keys into a new `.env` file (start from `.env.example`):

```bash
cp .env.example .env
# then paste VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY into .env
```

**Never commit `.env`** — it's already in `.gitignore`.

### 3. Run migrations

```bash
alembic upgrade head
```

(For local dev this is optional — the app also calls `create_all` on
startup — but it's how a real Postgres deploy gets its schema.)

### 4. (Optional) Generate app icons or seed demo phrases

Icons are already committed under `frontend/icons/`, but you can regenerate
them any time:

```bash
pip install Pillow   # dev-only, not a runtime dependency
python backend/scripts/generate_icons.py
```

To avoid staring at an empty Phrases list, seed a few starter phrases:

```bash
python -m backend.scripts.seed_demo_phrases
```

### 5. Run the app

```bash
uvicorn backend.main:app --reload
```

Open `http://localhost:8000`. Interactive API docs live at
`http://localhost:8000/docs`.

> **Push notifications need HTTPS** (localhost is exempted by browsers, but a
> real phone install needs a public HTTPS URL — see Deployment below).

### 6. Run the tests

```bash
pytest backend/tests -v   # 38 tests
ruff check .              # lint (also runs in CI)
```

### Alternative: run with Docker (real Postgres)

```bash
cp .env.example .env   # fill in VAPID keys as above
docker compose up --build
```

This builds the app image and a Postgres 16 container, runs
`alembic upgrade head` against real Postgres on boot, and serves on
`http://localhost:8000` — a closer approximation of the Render/Railway
production target than local SQLite.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `VAPID_PRIVATE_KEY` | yes | Private key from `generate_vapid_keys.py`. Never share. |
| `VAPID_PUBLIC_KEY` | yes | Public key; sent to the browser to subscribe. |
| `VAPID_CLAIMS_EMAIL` | yes | `mailto:` contact used in the VAPID JWT claim. |
| `DATABASE_URL` | yes | SQLAlchemy URL. Default: local SQLite file. Accepts a plain `postgres://`/`postgresql://` URL too — MindPulse rewrites it to the async driver automatically. |
| `ALLOWED_ORIGINS` | yes | Comma-separated CORS allow-list. |
| `ENVIRONMENT` | no | Free-text label, logged on startup. |

## API Reference

### Phrases — `/api/phrases`

| Method & Path | Status | Purpose |
|---|---|---|
| `GET /api/phrases` | 200 | All phrases (active + inactive) |
| `GET /api/phrases/random` | 200 / 404 | One random **active** phrase |
| `POST /api/phrases` | 201 | Create a phrase |
| `PATCH /api/phrases/{id}` | 200 / 404 | Update text, author, or `is_active` |
| `DELETE /api/phrases/{id}` | 204 / 404 | Hard delete |

### Push Subscriptions — `/api/subscriptions`

| Method & Path | Status | Purpose |
|---|---|---|
| `POST /api/subscriptions` | 201 | Register a browser push subscription |
| `DELETE /api/subscriptions` | 204 | Unregister by endpoint (in body) |

### Settings — `/api/settings`

| Method & Path | Status | Purpose |
|---|---|---|
| `GET /api/settings` | 200 | Current interval + running state |
| `PATCH /api/settings` | 200 | Change interval and/or pause/resume |
| `POST /api/settings/trigger` | 200 | Fire a notification immediately |

Full request/response schemas are in the auto-generated docs at `/docs`.

## Deployment (Render or Railway free tier)

1. Push this repo to GitHub.
2. **Render:** New → Blueprint → point at the repo (`render.yaml` is picked
   up automatically) → set the `VAPID_*` and `ALLOWED_ORIGINS` env vars in
   the dashboard (marked `sync: false` so they're never in git) → deploy.
   **Railway:** New Project → Deploy from GitHub → it detects the `Procfile`
   → add a Postgres plugin → set the same env vars → deploy.
3. Both platforms provide HTTPS automatically, which push notifications and
   `Add to Home Screen` both require.
4. Once live, open the public URL on a phone, tap **Add to Home Screen**,
   then **Enable Notifications** inside the installed app.

Either platform also happily builds straight from the `Dockerfile` instead of
the native Python buildpack, if you'd rather deploy the container as-is.

## License

MIT — see [LICENSE](LICENSE).

## Definition of Done

- [x] Installs to a mobile home screen and opens in standalone mode
- [x] Notifications arrive at the configured interval
- [x] All 8 user stories (see tech spec) pass their acceptance criteria
- [x] API endpoints return correct HTTP status codes
- [x] 38 pytest tests pass (well over the 10-test bar)
- [ ] Deployed to a public URL — see [Deployment](#deployment-render-or-railway-free-tier) above
- [x] README has setup, env vars, architecture diagram, screenshots
- [x] No secrets in git history (`.env` gitignored from commit #1)

## Built With Claude Code

This project followed a "pair programmer, not code generator" workflow:
design the module's structure and reasoning first, then generate one unit at
a time, then write the test before moving to the next unit. See the tech
spec's §11 for the exact prompting pattern used throughout.
