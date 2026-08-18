"""Lightweight admin/aggregation endpoint (spec round 3, item 4)."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.delivery_log import DeliveryLog
from backend.models.phrase import Phrase
from backend.models.subscription import PushSubscription
from backend.schemas.stats import MostSentPhrase, StatsOut

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get(
    "",
    response_model=StatsOut,
    summary="Aggregate counters for a lightweight admin view",
    description=(
        "Counts, not raw rows — cheap enough to poll from the Dashboard on every load. "
        "`notifications_sent_today` counts individual successful *deliveries* "
        "(delivery_log rows with status=delivered) since midnight UTC, not notification cycles."
    ),
)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_phrases = (await db.execute(select(func.count()).select_from(Phrase))).scalar_one()

    active_phrases = (
        await db.execute(select(func.count()).select_from(Phrase).where(Phrase.is_active.is_(True)))
    ).scalar_one()

    total_subscribers = (
        await db.execute(
            select(func.count()).select_from(PushSubscription).where(PushSubscription.is_active.is_(True))
        )
    ).scalar_one()

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    notifications_sent_today = (
        await db.execute(
            select(func.count())
            .select_from(DeliveryLog)
            .where(DeliveryLog.status == "delivered", DeliveryLog.created_at >= today_start)
        )
    ).scalar_one()

    top_phrase = (
        await db.execute(select(Phrase).where(Phrase.times_sent > 0).order_by(Phrase.times_sent.desc()).limit(1))
    ).scalar_one_or_none()

    return StatsOut(
        total_phrases=total_phrases,
        active_phrases=active_phrases,
        total_subscribers=total_subscribers,
        notifications_sent_today=notifications_sent_today,
        most_sent_phrase=MostSentPhrase.model_validate(top_phrase) if top_phrase else None,
    )
