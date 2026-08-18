"""
Web Push sending logic (VAPID-authenticated) via pywebpush.
"""
import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.subscription import PushSubscription

logger = logging.getLogger("mindpulse.push")


def _send_one(subscription: PushSubscription, payload: dict) -> bool:
    """Send to a single subscription. Returns True on success.

    Raises WebPushGone (via caller inspecting the exception) is not
    used here — instead we return False and let the caller decide
    whether the failure means "deactivate this subscription".
    """
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims=dict(settings.vapid_claims),
        )
        return True
    except WebPushException as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 410 or status_code == 404:
            # Gone / Not Found: the browser/OS push service says this
            # subscription no longer exists — safe to deactivate.
            logger.info("Subscription expired (status=%s), deactivating: %s", status_code, subscription.endpoint)
            raise _ExpiredSubscription() from exc
        logger.warning("Push send failed (status=%s): %s", status_code, exc)
        return False


class _ExpiredSubscription(Exception):
    """Internal signal that a subscription returned 410/404 Gone."""


async def send_to_all(db: AsyncSession, payload: dict) -> dict:
    """Send `payload` to every active subscription.

    Deactivates (soft-delete via is_active=False) any subscription the
    push service reports as gone, per spec 6.2.
    """
    result = await db.execute(select(PushSubscription).where(PushSubscription.is_active.is_(True)))
    subscriptions = result.scalars().all()

    delivered, expired, failed = 0, 0, 0
    for sub in subscriptions:
        try:
            ok = _send_one(sub, payload)
            if ok:
                delivered += 1
            else:
                failed += 1
        except _ExpiredSubscription:
            sub.is_active = False
            expired += 1

    if expired:
        await db.commit()

    return {
        "delivered": delivered,
        "expired": expired,
        "failed": failed,
        "total_subscriptions": len(subscriptions),
    }
