"""
FastAPI application entry point.

Run from the repo root with:
    uvicorn backend.main:app --reload
"""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.config import settings
from backend.database import init_models
from backend.logging_config import configure_logging, get_logger
from backend.rate_limit import limiter
from backend.routers import categories, phrases, stats, subscriptions
from backend.routers import settings as settings_router
from backend.services import scheduler as scheduler_service

configure_logging()
logger = get_logger("mindpulse")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

API_DESCRIPTION = """
MindPulse pushes short, user-curated motivational phrases to a browser
on a configurable schedule via the Web Push API.

### Notes
- All mutating endpoints validate input with Pydantic — expect `422` on
  bad payloads, not silent coercion.
- `POST /api/phrases` and `POST /api/settings/trigger` are rate-limited
  (see each endpoint's description) to keep a publicly-deployed instance
  from being hammered.
- Every response carries an `X-Request-ID` header; include it when
  reporting a bug and it'll be in the structured server logs verbatim.
"""

OPENAPI_TAGS = [
    {"name": "phrases", "description": "CRUD for the motivational phrases MindPulse sends."},
    {"name": "categories", "description": "Tags phrases can belong to, used to filter what gets sent."},
    {"name": "subscriptions", "description": "Browser Web Push subscription registration."},
    {"name": "settings", "description": "Delivery interval, pause/resume, category filter, manual trigger."},
    {"name": "stats", "description": "Aggregate counters for a lightweight admin view."},
    {"name": "meta", "description": "Health check and VAPID public key."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    # create_all is idempotent (checkfirst), so this is safe to run every
    # boot for local/dev SQLite. Alembic (backend/alembic/) is the source
    # of truth for production migrations against Postgres.
    await init_models()
    await scheduler_service.start_scheduler()
    logger.info("app_started", environment=settings.environment)

    yield

    # --- shutdown ---
    await scheduler_service.shutdown_scheduler()
    logger.info("app_shutdown")


app = FastAPI(
    title="MindPulse",
    version="1.1.0",
    summary="Scheduled motivational push notifications, delivered like a native app.",
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": f"Rate limit exceeded: {exc.detail}"})


app.add_middleware(SlowAPIMiddleware)


class RequestIDMiddleware:
    """Bare-ASGI middleware: stamps every request with a UUID, binds it into
    structlog's contextvars (so every log line during the request carries
    it automatically), and echoes it back as `X-Request-ID`."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_with_header)


app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(phrases.router)
app.include_router(subscriptions.router)
app.include_router(settings_router.router)
app.include_router(categories.router)
app.include_router(stats.router)


@app.get(
    "/api/health",
    tags=["meta"],
    summary="Liveness check",
    response_description="Always `{\"status\": \"ok\"}` if the process is up.",
)
async def health():
    return {"status": "ok"}


@app.get(
    "/api/vapid-public-key",
    tags=["meta"],
    summary="Fetch the VAPID public key",
    response_description="The base64url-encoded public key to pass as `applicationServerKey`.",
)
async def vapid_public_key():
    """The frontend fetches this instead of hardcoding the key in app.js,
    so rotating VAPID keys doesn't require a frontend deploy."""
    return {"publicKey": settings.vapid_public_key}


# Serve the PWA frontend. Mounted last so /api/* routes above always win.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
