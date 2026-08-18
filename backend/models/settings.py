from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.category import settings_categories


class AppSettings(Base):
    """Singleton row (id is always 1) holding global scheduler config."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    is_running: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Empty = no filter, send from every active phrase regardless of tags.
    active_categories: Mapped[list["Category"]] = relationship(  # noqa: F821
        secondary=settings_categories, lazy="selectin"
    )
