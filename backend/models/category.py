"""
Categories/tags for phrases (many-to-many), plus a second many-to-many
between AppSettings and Category used as the "only send from these
categories" filter (spec-round-3 item 5).

Two separate association tables rather than one shared one: a phrase's
tags and the scheduler's active filter are conceptually different
relationships that happen to point at the same Category rows, and
sharing a table would make the ORM relationships ambiguous.
"""
from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

phrase_categories = Table(
    "phrase_categories",
    Base.metadata,
    Column("phrase_id", Integer, ForeignKey("phrases.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)

settings_categories = Table(
    "settings_categories",
    Base.metadata,
    Column("settings_id", Integer, ForeignKey("app_settings.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)

    phrases: Mapped[list["Phrase"]] = relationship(  # noqa: F821
        secondary=phrase_categories, back_populates="categories", lazy="selectin"
    )
