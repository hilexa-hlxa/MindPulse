from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.subscription import PushSubscription
from backend.schemas.subscription import SubscriptionCreate, SubscriptionDelete, SubscriptionOut

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


@router.post(
    "",
    response_model=SubscriptionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a browser push subscription",
    description=(
        "Body mirrors `PushSubscription.toJSON()` from the browser's Push API. Idempotent: "
        "re-subscribing with an endpoint that's already registered reactivates/updates that row "
        "(e.g. after the browser rotates keys) instead of erroring on the UNIQUE constraint."
    ),
)
async def create_subscription(payload: SubscriptionCreate, db: AsyncSession = Depends(get_db)):
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


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister a push subscription",
    description="Unknown endpoints still return 204 — 'not subscribed' already holds, so it's a no-op, not an error.",
)
async def delete_subscription(payload: SubscriptionDelete, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    subscription = result.scalar_one_or_none()
    if subscription:
        await db.delete(subscription)
        await db.commit()
    return None
