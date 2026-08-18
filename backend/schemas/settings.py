from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SettingsUpdate(BaseModel):
    interval_minutes: int | None = Field(default=None, ge=15, le=240, description="Minutes between sends, 15-240.")
    is_running: bool | None = None
    category_filter: list[str] | None = Field(
        default=None,
        max_length=10,
        description=(
            "REPLACES the active category filter. An empty list clears the filter "
            "(send from every active phrase); omit the field entirely to leave it unchanged."
        ),
        examples=[["discipline", "focus"]],
    )


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    interval_minutes: int
    is_running: bool
    last_sent_at: datetime | None
    # The ORM attribute is `active_categories` (a list[Category]); the API
    # field is `category_filter` (a list[str]) — the alias tells
    # from_attributes where to actually read the value from, since the
    # names don't match and it won't guess.
    category_filter: list[str] = Field(default_factory=list, validation_alias="active_categories")

    @field_validator("category_filter", mode="before")
    @classmethod
    def _category_names(cls, value):
        if value and hasattr(value[0], "name"):
            return sorted(c.name for c in value)
        return value


class TriggerResult(BaseModel):
    sent: bool
    reason: str | None = None
