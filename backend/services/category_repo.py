"""
Get-or-create helper for category names, shared by the phrases router
(tagging a phrase) and the settings router (the send-filter selection).

Names are normalized (trimmed, lowercased) so "Focus" and "focus" typed
in two different places resolve to the same row instead of silently
fragmenting into duplicate tags.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.category import Category


def normalize_names(names: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = raw.strip().lower()
        if name and name not in seen:
            seen.add(name)
            cleaned.append(name)
    return cleaned


async def get_or_create_categories(db: AsyncSession, names: list[str]) -> list[Category]:
    cleaned = normalize_names(names)
    if not cleaned:
        return []

    result = await db.execute(select(Category).where(Category.name.in_(cleaned)))
    existing = {c.name: c for c in result.scalars().all()}

    categories = []
    for name in cleaned:
        category = existing.get(name)
        if category is None:
            category = Category(name=name)
            db.add(category)
            existing[name] = category
        categories.append(category)

    await db.flush()  # assign PKs to any newly-created rows; caller commits
    return categories
