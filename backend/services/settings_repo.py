"""
Shared accessor for the app_settings singleton row.

Both the /api/settings router and the scheduler service need to read
(and occasionally lazily create) this row, so it lives here instead
of being duplicated.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.settings import AppSettings

SETTINGS_ROW_ID = 1


async def get_or_create_settings(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSettings).where(AppSettings.id == SETTINGS_ROW_ID))
    row = result.scalar_one_or_none()
    if row is None:
        row = AppSettings(id=SETTINGS_ROW_ID)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row
