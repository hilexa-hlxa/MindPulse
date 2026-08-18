"""
Shared "pick one random active phrase" query, respecting the settings'
active category filter (if any). Used by both `GET /api/phrases/random`
(the Dashboard preview button) and the scheduler's send job, so the
preview always shows exactly what would actually get sent.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.category import Category
from backend.models.phrase import Phrase
from backend.services.settings_repo import get_or_create_settings


async def pick_random_active_phrase(db: AsyncSession) -> Phrase | None:
    app_settings = await get_or_create_settings(db)
    category_names = [c.name for c in app_settings.active_categories]

    stmt = select(Phrase).where(Phrase.is_active.is_(True))
    if category_names:
        # A phrase with 2+ matching tags shouldn't be 2x more likely to be
        # picked, so filter via a DISTINCT id subquery rather than joining
        # + distinct()-ing the outer query directly: Postgres rejects
        # `SELECT DISTINCT ... ORDER BY random()` because random() isn't in
        # the select list (SQLite silently allows it — this only surfaces
        # against real Postgres, which is exactly why it's worth testing
        # against). Keeping DISTINCT confined to the subquery, with no
        # ORDER BY there, sidesteps the conflict entirely.
        matching_ids = (
            select(Phrase.id).join(Phrase.categories).where(Category.name.in_(category_names)).distinct()
        )
        stmt = stmt.where(Phrase.id.in_(matching_ids))
    stmt = stmt.order_by(func.random()).limit(1)

    return (await db.execute(stmt)).scalar_one_or_none()
