"""
Web Push sending logic (VAPID-authenticated) via pywebpush, with retry.
"""
import asyncio
import json

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.logging_config import get_logger
from backend.models.delivery_log import DeliveryLog
from backend.models.subscription import PushSubscription

logger = get_logger("mindpulse.push")

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = [1, 2]  # wait before attempt 2, then before attempt 3

# Indirection so tests can monkeypatch just the sleep call (instant retries)
# without touching the real asyncio module.
_sleep = asyncio.sleep


async def _send_with_retry(subscription: PushSubscription, payload: dict) -> tuple[str, int, str | None]:
    """Attempt delivery up to MAX_ATTEMPTS times with exponential backoff
    for transient failures. A 410/404 Gone/Not Found short-circuits
    immediately — retrying a dead subscription just wastes time.

    Returns (status, attempts_made, error_message) where status is one of
    "delivered" | "expired" | "failed".
    """
    last_error: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            # pywebpush's webpush() is a blocking call; run it off the event
            # loop so one slow push service doesn't stall every other
            # request the server is handling concurrently.
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=dict(settings.vapid_claims),
            )
            return "delivered", attempt, None
        except WebPushException as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code in (404, 410):
                return "expired", attempt, f"push service returned {status_code}"
            last_error = f"WebPushException (status={status_code}): {exc}"
        except Exception as exc:  # network errors, timeouts, etc.
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < MAX_ATTEMPTS:
            logger.warning(
                "push_attempt_failed",
                endpoint=subscription.endpoint,
                attempt=attempt,
                error=last_error,
            )
            await _sleep(RETRY_BACKOFF_SECONDS[attempt - 1])

    return "failed", MAX_ATTEMPTS, last_error


async def send_to_all(db: AsyncSession, phrase_id: int, payload: dict) -> dict:
    """Send `payload` to every active subscription, retrying transient
    failures and recording one delivery_log row per subscription."""
    result = await db.execute(select(PushSubscription).where(PushSubscription.is_active.is_(True)))
    subscriptions = result.scalars().all()

    delivered, expired, failed = 0, 0, 0
    for sub in subscriptions:
        status_, attempts, error = await _send_with_retry(sub, payload)

        db.add(
            DeliveryLog(
                phrase_id=phrase_id,
                endpoint=sub.endpoint,
                status=status_,
                attempts=attempts,
                error=error,
            )
        )

        if status_ == "delivered":
            delivered += 1
        elif status_ == "expired":
            sub.is_active = False
            expired += 1
            logger.info("subscription_expired", endpoint=sub.endpoint)
        else:
            failed += 1
            logger.error("push_delivery_failed", endpoint=sub.endpoint, attempts=attempts, error=error)

    await db.commit()

    return {
        "delivered": delivered,
        "expired": expired,
        "failed": failed,
        "total_subscriptions": len(subscriptions),
    }
