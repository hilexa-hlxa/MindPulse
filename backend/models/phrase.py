from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.category import phrase_categories


class Phrase(Base):
    __tablename__ = "phrases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    times_sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    categories: Mapped[list["Category"]] = relationship(  # noqa: F821
        secondary=phrase_categories, back_populates="phrases", lazy="selectin"
    )
