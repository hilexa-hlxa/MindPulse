from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PhraseCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=120)


class PhraseUpdate(BaseModel):
    """All fields optional — PATCH semantics, only provided fields change."""

    text: str | None = Field(default=None, min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class PhraseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    author: str | None
    is_active: bool
    times_sent: int
    created_at: datetime
