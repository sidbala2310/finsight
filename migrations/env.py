"""Alembic environment: connect migrations to the application's database settings."""

from alembic import context
from sqlalchemy import create_engine, pool

from finsight.config import get_settings


def _sync_database_url() -> str:
    """The app connects with asyncpg; migrations use the sync psycopg driver."""
    url = get_settings().database_url
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def apply_migrations() -> None:
    engine = create_engine(_sync_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()  # hand control back to Alembic


apply_migrations()
