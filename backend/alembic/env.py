import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make `backend.*` importable when Alembic is invoked as `alembic ...`
# from the repo root (this file lives at backend/alembic/env.py).
from backend.config import settings as app_settings
from backend.database import Base
from backend.models import AppSettings, Phrase, PushSubscription  # noqa: F401  (populate metadata)

config = context.config

# Use the app's own DATABASE_URL instead of the static value in
# alembic.ini, so migrations always target whatever .env points at.
config.set_main_option("sqlalchemy.url", app_settings.async_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Async engine variant, since the app uses aiosqlite/asyncpg drivers."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
