# Deploying MindPulse

Everything you need to know to take this from `localhost:8000` to a real
public URL, written from the actual errors we hit getting there — not just
the happy path.

Read **[Before you start](#before-you-start)** first even if you're in a
hurry — it explains why the platform choice isn't arbitrary and will save
you a broken deploy.

---

## Before you start

**MindPulse needs a long-running process.** The whole point of the app is
`AsyncIOScheduler` firing every N minutes *inside the running Python
process*. That rules out pure serverless platforms (Vercel, Netlify
Functions, AWS Lambda) for the backend — a serverless function starts,
handles one request, and dies. There's no "N minutes later" for it to wake
up in. Vercel-for-backend will deploy "successfully" and just never send a
notification, silently.

**Two deployment shapes work:**

| Shape | Where | Effort | When to use it |
|---|---|---|---|
| **A. Single service** | Render or Railway, backend serves the frontend too | Lowest — one deploy, no config | You just want it live |
| **B. Split** | Frontend on Vercel (CDN), backend on Railway | One extra step (a URL to paste in) | You specifically want the frontend on Vercel's CDN |

If you don't have a strong reason to want shape B, **pick shape A** — it's
what the app already does locally (`backend/main.py` mounts `frontend/` as
static files), it's what `render.yaml` and `Procfile` are already set up
for, and there's nothing extra to misconfigure.

This guide covers both. Shape A first.

---

## Shape A: single service (Render or Railway)

### 1. Pick a database

MindPulse defaults to a local SQLite file (`backend/config.py:22`) unless
you set `DATABASE_URL`. **Do not deploy on the SQLite default** — most
platform filesystems are ephemeral, so the database gets wiped on every
redeploy/restart, silently, with no error. You need a real Postgres
instance. Two ways to get one:

- **Platform-managed**: Render's Blueprint (`render.yaml`) provisions one
  automatically. Railway: add a Postgres plugin to your project.
- **Supabase** (or any external Postgres): free tier, works fine. Use the
  **Session pooler** connection string (port `5432`), not the Transaction
  pooler (port `6543`) — MindPulse's async engine (`asyncpg`) relies on
  prepared statements, which the transaction pooler's connection
  multiplexing breaks. The session pooler string looks like:
  ```
  postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
  ```

Either way, you end up with one `DATABASE_URL` value. `config.py`
transparently rewrites a plain `postgres://`/`postgresql://` URL to the
`asyncpg` driver — paste the connection string as-is, no manual edits
needed.

**If you're using Supabase specifically**: MindPulse only uses it as a
Postgres host (no Supabase Auth/Storage/client libraries), but Supabase's
`public` schema is exposed through its own Data API by default. This app's
`push_subscriptions` table holds Web Push credentials — check Supabase
dashboard → **Data API** settings and either disable the Data API for this
project, or enable RLS with no policies on these tables as a deny-all,
since your backend connects directly and doesn't need the Data API at all.

### 2. Generate a VAPID key pair

Web Push requires this. Run locally, once:
```bash
python backend/scripts/generate_vapid_keys.py
```
Save both keys somewhere — you'll paste them as env vars in step 4. This
keypair is specific to this deployment; don't reuse your local dev `.env`
keypair for production (and never commit either to git — `.gitignore`
already excludes `.env`).

### 3. Deploy

**Render**: New → Blueprint → point at this repo. `render.yaml` handles
the rest (build command, start command, and — if you use Render's own
Postgres — the database wiring) automatically.

**Railway**: New Project → Deploy from GitHub repo → it should detect
`Procfile` (`alembic upgrade head && uvicorn backend.main:app ...`) and
use that as the start command automatically.

**Gotcha we actually hit**: Railway's auto-builder (Railpack/Nixpacks)
has its own Python/FastAPI entrypoint auto-detector that runs *before* it
considers the `Procfile`, and it only looks in a short list of
conventional locations (`main.py`, `app.py`, etc.) — not `backend/main.py`,
where this app's entrypoint actually lives. If your deploy fails with:
```
Error: No FastAPI entrypoint found in default locations, but found
potential entrypoints: backend/main.py (variable: app)
```
force it to skip auto-detection entirely — either:
- Service Settings → Build → set **Builder** to **Dockerfile** (this repo
  has one, already tested against real Postgres — see
  [Verify it actually worked](#5-verify-it-actually-worked)), or
- Set a **Custom Start Command** explicitly:
  `alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

A `railway.json` isn't included in this repo (dashboard settings are
enough), but if you want it version-controlled instead of a manual
dashboard click, add:
```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": { "builder": "DOCKERFILE" }
}
```

### 4. Set environment variables

On whichever platform, set these on the web service:

| Variable | Value |
|---|---|
| `VAPID_PRIVATE_KEY` | from step 2 |
| `VAPID_PUBLIC_KEY` | from step 2 |
| `VAPID_CLAIMS_EMAIL` | `mailto:you@example.com` |
| `DATABASE_URL` | from step 1 — **plain text value** if it's Supabase/external Postgres; if it's Railway's own Postgres plugin, use **Add Reference** → pick the Postgres service's `DATABASE_URL` instead of typing it (adding the plugin does *not* auto-inject it into your web service — this is a separate step people miss) |
| `ALLOWED_ORIGINS` | your deployed URL, e.g. `https://mindpulse.up.railway.app` |
| `ENVIRONMENT` | `production` |

Redeploy after setting these if the platform doesn't do it automatically.

### 5. Verify it actually worked

Don't trust a green "Deployed" checkmark — check what it actually did:

1. **Check the deploy/boot logs** for the Alembic migration lines. You
   want to see:
   ```
   Context impl PostgresqlImpl.
   Running upgrade  -> 5c09be5147e5, initial schema...
   Running upgrade 5c09be5147e5 -> bb321ca7de78, add categories...
   ```
   If it says `Context impl SQLiteImpl` instead, `DATABASE_URL` isn't
   wired up — go back to step 4. This is the exact failure mode that bit
   us: the deploy "succeeds" and silently runs on ephemeral SQLite.
2. `curl https://your-url/api/health` → `{"status":"ok"}`
3. `curl https://your-url/api/stats` → should return real zeros, not an
   error (confirms the DB tables exist and are queryable)
4. Open the URL on your phone, **Add to Home Screen**, tap **Enable
   Notifications**, then **Send now** on the Dashboard, confirm a real
   notification arrives. If it doesn't:
   - Check `Notification.permission` is `granted` and a push subscription
     exists (DevTools → Application → Service Workers)
   - Check the deploy logs for a `notification_sent` event with
     `delivered: 1` — if it says `delivered: 0`, the push reached your
     server but not the browser's push service
   - If the server logs show success but nothing appears on-device, it's
     almost always an **OS-level notification setting**, not the app —
     on macOS specifically, check System Settings → Notifications for
     the exact browser app you're using (there can be multiple entries
     for different Chrome channels/reinstalls), and check Focus/Do Not
     Disturb isn't swallowing the banner.

---

## Shape B: split — Vercel (frontend) + Railway (backend)

Do **Shape A's steps 1–2 and 4–5 for the Railway backend first** (skip its
step 3's "deploy the whole app" framing — you're deploying just the
backend, same steps otherwise). Once that backend is live and verified,
come back here.

### 1. Point the frontend at your backend

`frontend/vercel.json` reverse-proxies `/api/*` to your Railway backend —
the frontend keeps calling relative `/api/...` paths exactly as it does
locally (zero JS changes), and since the browser only ever sees Vercel's
own origin, **CORS never enters the picture at all**: this is a
server-to-server proxy hop, not a cross-origin browser request. Edit the
file:
```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://YOUR-RAILWAY-URL/api/:path*" }
  ]
}
```
Replace `YOUR-RAILWAY-URL` with your actual Railway backend URL from
Shape A. Commit and push.

### 2. Deploy to Vercel

1. vercel.com → Add New → Project → import this repo.
2. **Root Directory: `frontend`** — this is the step that's easy to skip,
   and skipping it is exactly what broke our first attempt: without it,
   Vercel scans the *whole* repo, finds `requirements.txt` +
   `backend/main.py` at the root, and tries to auto-detect it as a
   Python/FastAPI project instead of a static site — producing the exact
   same "No FastAPI entrypoint found" error as the Railway gotcha above,
   for the same underlying reason (auto-detection scanning the wrong
   directory). Setting Root Directory to `frontend` means Vercel never
   sees the Python code at all.
3. Framework Preset: **Other** (no build step — it's plain HTML/JS).
4. Deploy.
5. (Optional, defense-in-depth) Set `ALLOWED_ORIGINS` on the Railway
   backend to your Vercel URL. Not required for the app to function (see
   the CORS note above), but reasonable if the API is ever called
   directly from somewhere else.

### 3. Verify

- Open the Vercel URL. DevTools → Network tab: requests to `/api/...`
  should return 200s (proxied through to Railway).
- Same on-device notification test as Shape A step 5.4.
- The service worker registers on the Vercel origin (same origin as the
  page, which is required) — its push subscription POST rides the same
  `/api/*` proxy, so if notifications work, the whole chain is confirmed
  end to end.

---

## Environment variable reference

| Variable | Required | Notes |
|---|---|---|
| `VAPID_PRIVATE_KEY` | yes | From `generate_vapid_keys.py`. Never commit, never share outside your deploy platform's secret store. |
| `VAPID_PUBLIC_KEY` | yes | Sent to the browser to create the push subscription. Not secret. |
| `VAPID_CLAIMS_EMAIL` | yes | `mailto:` contact used in the VAPID JWT claim. |
| `DATABASE_URL` | yes | Real Postgres in production — see [Pick a database](#1-pick-a-database). Plain `postgres://`/`postgresql://` is rewritten to the async driver automatically. |
| `ALLOWED_ORIGINS` | yes | Comma-separated CORS allow-list. Only matters for direct cross-origin calls to the API — irrelevant for the Vercel rewrite-proxy setup, but keep it accurate anyway. |
| `ENVIRONMENT` | no | Free-text label, shows up in structured logs on boot (`environment=production`). |

---

## Post-deploy checklist

- [ ] Boot/deploy logs show `Context impl PostgresqlImpl`, not `SQLiteImpl`
- [ ] `GET /api/health` returns `{"status":"ok"}`
- [ ] `GET /api/stats` returns real data, not a 500
- [ ] App installs to a phone home screen and opens in standalone mode
- [ ] Enable Notifications → Send now → a real notification arrives on-device
- [ ] Deploy logs show a `notification_sent` event with `delivered: 1` after that test
- [ ] No secrets committed — double-check `git log --all -p | grep -i vapid_private` comes back empty before making the repo public
- [ ] (Supabase only) Data API disabled or RLS enabled on `push_subscriptions`

## If something's still broken

Check the structured JSON logs first (`structlog` — every line is a JSON
object; look for `"level": "error"` or a Python traceback under
`"exception"`). The request that failed carries an `X-Request-ID` response
header that matches a `request_id` field in the logs, so you can find the
exact failing request even in a busy log stream.
