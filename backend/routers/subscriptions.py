from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.subscription import PushSubscription
from backend.schemas.subscription import SubscriptionCreate, SubscriptionDelete, SubscriptionOut

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
async def create_subscription(payload: SubscriptionCreate, db: AsyncSession = Depends(get_db)):
    """Register a browser push subscription.

    Idempotent: re-subscribing with the same endpoint (e.g. after the
    browser rotates keys, or the tab reloads) reactivates/updates the
    existing row instead of violating the UNIQUE constraint on endpoint.
    """
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return existing

    subscription = PushSubscription(
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(payload: SubscriptionDelete, db: AsyncSession = Depends(get_db)):
    """Unregister a subscription by endpoint. No-op (still 204) if unknown,
    since the end state the client wants — 'not subscribed' — already holds."""
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    subscription = result.scalar_one_or_none()
    if subscription:
        await db.delete(subscription)
        await db.commit()
    return None
