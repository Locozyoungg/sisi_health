"""Alembic environment. The URL comes from app settings (SISI_DATABASE_URL or the
TEST override); every migration is forward-only and carries a rollback note."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import Settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings(_env_file=None)
database_url = os.environ.get("SISI_ALEMBIC_URL", settings.database_url)
if os.environ.get("SISI_TEST_DATABASE_URL"):
    database_url = os.environ["SISI_TEST_DATABASE_URL"]

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
