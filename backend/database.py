"""
Async SQLAlchemy engine + session setup.

Uses SQLAlchemy 2.0's async engine (aiosqlite driver for local dev,
psycopg for Postgres in production — swap via DATABASE_URL).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

engine = create_async_engine(settings.async_database_url, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_models() -> None:
    """Create tables directly from ORM metadata.

    Used for local/dev bootstrap and for the test suite so a fresh
    SQLite file/in-memory DB always has the current schema, without
    requiring Alembic to run first. Alembic remains the source of
    truth for production migrations (see backend/alembic/).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
