"""
Background notification scheduling via APScheduler.

Uses AsyncIOScheduler (not BackgroundScheduler) because the job body
(`send_random_notification`) is a coroutine that awaits DB queries and
network calls to the push service — AsyncIOScheduler runs jobs on the
same asyncio event loop FastAPI/uvicorn already has running, so an
`async def` job can be awaited directly instead of needing a thread.
"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select

from backend.database import AsyncSessionLocal
from backend.models.phrase import Phrase
from backend.services.push import send_to_all
from backend.services.settings_repo import get_or_create_settings

logger = logging.getLogger("mindpulse.scheduler")

JOB_ID = "notification_job"

scheduler = AsyncIOScheduler()


async def send_random_notification() -> dict:
    """Core delivery job (spec 6.2):

    1. Query one random active phrase.
    2. Fetch all active push subscriptions.
    3. Send a Web Push payload to each via pywebpush.
    4. Deactivate any subscription the push service reports as gone.
    5. Increment times_sent on the phrase.
    6. Update app_settings.last_sent_at.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Phrase).where(Phrase.is_active.is_(True)).order_by(func.random()).limit(1)
        )
        phrase = result.scalar_one_or_none()
        if phrase is None:
            logger.info("No active phrases — skipping notification cycle.")
            return {"sent": False, "reason": "no active phrases"}

        payload = {"title": "MindPulse", "body": phrase.text, "author": phrase.author}
        push_result = await send_to_all(db, payload)

        phrase.times_sent += 1
        app_settings = await get_or_create_settings(db)
        app_settings.last_sent_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("Sent phrase #%s to %s subscriber(s).", phrase.id, push_result["delivered"])
        return {"sent": True, "phrase_id": phrase.id, **push_result}


def reschedule(interval_minutes: int, is_running: bool) -> None:
    """Re-read config and apply it to the live scheduler without a restart
    (spec 6.1: "re-read on every PATCH /api/settings call")."""
    if not is_running:
        if scheduler.get_job(JOB_ID):
            scheduler.remove_job(JOB_ID)
        return

    scheduler.add_job(
        send_random_notification,
        "interval",
        minutes=interval_minutes,
        id=JOB_ID,
        replace_existing=True,
    )


async def start_scheduler() -> None:
    """Called from the FastAPI startup event."""
    async with AsyncSessionLocal() as db:
        app_settings = await get_or_create_settings(db)

    if not scheduler.running:
        scheduler.start()
    reschedule(app_settings.interval_minutes, app_settings.is_running)


async def shutdown_scheduler() -> None:
    """Called from the FastAPI shutdown event."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
