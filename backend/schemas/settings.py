from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SettingsUpdate(BaseModel):
    interval_minutes: int | None = Field(default=None, ge=15, le=240)
    is_running: bool | None = None


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interval_minutes: int
    is_running: bool
    last_sent_at: datetime | None


class TriggerResult(BaseModel):
    sent: bool
    reason: str | None = None
