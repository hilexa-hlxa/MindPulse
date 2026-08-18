"""
Background notification scheduling via APScheduler.

Uses AsyncIOScheduler (not BackgroundScheduler) because the job body
(`send_random_notification`) is a coroutine that awaits DB queries and
network calls to the push service — AsyncIOScheduler runs jobs on the
same asyncio event loop FastAPI/uvicorn already has running, so an
`async def` job can be awaited directly instead of needing a thread.
"""
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.database import AsyncSessionLocal
from backend.logging_config import get_logger
from backend.services.phrase_repo import pick_random_active_phrase
from backend.services.push import send_to_all
from backend.services.settings_repo import get_or_create_settings

logger = get_logger("mindpulse.scheduler")

JOB_ID = "notification_job"

scheduler = AsyncIOScheduler()


async def send_random_notification() -> dict:
    """Core delivery job (spec 6.2, extended with category filtering):

    1. Query one random active phrase, restricted to the settings'
       active category filter if one is set.
    2. Fetch all active push subscriptions.
    3. Send a Web Push payload to each via pywebpush, with retry.
    4. Deactivate any subscription the push service reports as gone.
    5. Increment times_sent on the phrase.
    6. Update app_settings.last_sent_at.
    """
    async with AsyncSessionLocal() as db:
        app_settings = await get_or_create_settings(db)
        category_names = [c.name for c in app_settings.active_categories]

        phrase = await pick_random_active_phrase(db)
        if phrase is None:
            logger.info("notification_skipped", reason="no_active_phrases", category_filter=category_names)
            return {"sent": False, "reason": "no active phrases"}

        payload = {"title": "MindPulse", "body": phrase.text, "author": phrase.author}
        push_result = await send_to_all(db, phrase.id, payload)

        phrase.times_sent += 1
        app_settings.last_sent_at = datetime.now(UTC)
        await db.commit()

        logger.info(
            "notification_sent",
            phrase_id=phrase.id,
            subscriber_count=push_result["total_subscriptions"],
            delivered=push_result["delivered"],
            expired=push_result["expired"],
            failed=push_result["failed"],
            category_filter=category_names,
        )
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
