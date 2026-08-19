from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.rate_limit import limiter
from backend.schemas.settings import SettingsOut, SettingsUpdate, TriggerResult
from backend.services import scheduler as scheduler_service
from backend.services.category_repo import get_or_create_categories
from backend.services.settings_repo import get_or_create_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut, summary="Get current settings")
async def get_settings_endpoint(db: AsyncSession = Depends(get_db)):
    return await get_or_create_settings(db)


@router.patch(
    "",
    response_model=SettingsOut,
    summary="Change interval, pause/resume, or the category filter",
    description="Applies to the live scheduler immediately — no server restart needed (US-06 / US-08).",
)
async def update_settings(payload: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    app_settings = await get_or_create_settings(db)

    updates = payload.model_dump(exclude_unset=True, exclude={"category_filter"})
    for field, value in updates.items():
        setattr(app_settings, field, value)

    if payload.category_filter is not None:
        app_settings.active_categories = await get_or_create_categories(db, payload.category_filter)

    await db.commit()
    await db.refresh(app_settings)

    # Apply the new interval/pause-state to the live scheduler immediately,
    # without requiring a server restart (spec US-06 / US-08).
    scheduler_service.reschedule(app_settings.interval_minutes, app_settings.is_running)

    return app_settings


@router.post(
    "/trigger",
    response_model=TriggerResult,
    summary="Send a notification right now",
    description="Fires immediately regardless of the schedule (US-07). "
    "Rate-limited to 15 requests/minute per client.",
)
@limiter.limit("15/minute")
async def trigger_notification(request: Request):
    result = await scheduler_service.send_random_notification()
    return TriggerResult(sent=result["sent"], reason=result.get("reason"))
