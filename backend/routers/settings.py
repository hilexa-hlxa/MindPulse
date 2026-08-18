from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.settings import SettingsOut, SettingsUpdate, TriggerResult
from backend.services import scheduler as scheduler_service
from backend.services.settings_repo import get_or_create_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings_endpoint(db: AsyncSession = Depends(get_db)):
    return await get_or_create_settings(db)


@router.patch("", response_model=SettingsOut)
async def update_settings(payload: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    app_settings = await get_or_create_settings(db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(app_settings, field, value)

    await db.commit()
    await db.refresh(app_settings)

    # Apply the new interval/pause-state to the live scheduler immediately,
    # without requiring a server restart (spec US-06 / US-08).
    scheduler_service.reschedule(app_settings.interval_minutes, app_settings.is_running)

    return app_settings


@router.post("/trigger", response_model=TriggerResult)
async def trigger_notification():
    """Manually fire a notification now, regardless of the schedule (US-07)."""
    result = await scheduler_service.send_random_notification()
    return TriggerResult(sent=result["sent"], reason=result.get("reason"))
