"""
FastAPI application entry point.

Run from the repo root with:
    uvicorn backend.main:app --reload
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import init_models
from backend.routers import phrases, settings as settings_router, subscriptions
from backend.services import scheduler as scheduler_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mindpulse")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    # create_all is idempotent (checkfirst), so this is safe to run every
    # boot for local/dev SQLite. Alembic (backend/alembic/) is the source
    # of truth for production migrations against Postgres.
    await init_models()
    await scheduler_service.start_scheduler()
    logger.info("MindPulse started (environment=%s).", settings.environment)

    yield

    # --- shutdown ---
    await scheduler_service.shutdown_scheduler()
    logger.info("MindPulse shut down.")


app = FastAPI(title="MindPulse", version="1.0.0", lifespan=lifespan)

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


@app.get("/api/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/api/vapid-public-key", tags=["meta"])
async def vapid_public_key():
    """Frontend fetches this instead of hardcoding the key in app.js."""
    return {"publicKey": settings.vapid_public_key}


# Serve the PWA frontend. Mounted last so /api/* routes above always win.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
