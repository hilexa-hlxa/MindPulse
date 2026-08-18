from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


def _normalize_author(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class PhraseCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500, examples=["Make it first, make it great later."])
    author: str | None = Field(default=None, max_length=120, examples=["Unknown"])
    categories: list[str] | None = Field(
        default=None,
        max_length=10,
        description="Tag names, e.g. ['discipline', 'focus']. Unknown names are created automatically.",
        examples=[["discipline", "focus"]],
    )

    _clean_text = field_validator("text")(_normalize_text)
    _clean_author = field_validator("author")(_normalize_author)


class PhraseUpdate(BaseModel):
    """All fields optional — PATCH semantics, only provided fields change."""

    text: str | None = Field(default=None, min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    categories: list[str] | None = Field(
        default=None,
        max_length=10,
        description="If provided, REPLACES the phrase's tag set (not a merge).",
    )

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        return _normalize_text(value) if value is not None else None

    _clean_author = field_validator("author")(_normalize_author)


class PhraseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    author: str | None
    is_active: bool
    times_sent: int
    created_at: datetime
    categories: list[str] = Field(default_factory=list)

    @field_validator("categories", mode="before")
    @classmethod
    def _category_names(cls, value):
        # `value` is a list of Category ORM objects (from the relationship)
        # on the create/read path, or already a list[str] in tests that
        # build PhraseOut directly — handle both.
        if value and hasattr(value[0], "name"):
            return sorted(c.name for c in value)
        return value
