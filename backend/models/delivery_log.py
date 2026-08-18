from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class DeliveryLog(Base):
    """One row per (notification cycle, subscription) delivery attempt.

    `endpoint` is stored as a snapshot string rather than a strict FK to
    push_subscriptions, deliberately: an expired subscription gets
    deactivated (or later hard-deleted) right after this row is written,
    and the log should still show what was attempted even if the
    subscription it targeted no longer exists.
    """

    __tablename__ = "delivery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phrase_id: Mapped[int] = mapped_column(ForeignKey("phrases.id", ondelete="CASCADE"), nullable=False)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # delivered | expired | failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
