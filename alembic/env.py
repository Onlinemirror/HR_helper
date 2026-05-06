"""Alembic env.py — настроен для async SQLAlchemy и чтения URL из .env."""
import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool

from alembic import context

# Добавляем корень проекта в sys.path чтобы импортировать models и config
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from models.base import Base
# Импортируем модели явно — иначе autogenerate их не увидит
import models.onboarding  # noqa: F401

target_metadata = Base.metadata

alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# URL берём из переменной окружения, не из alembic.ini
DATABASE_URL = os.getenv("DATABASE_URL", "")


def run_migrations_offline() -> None:
    """Offline-режим: генерирует SQL без подключения к БД."""
    context.configure(
        url=DATABASE_URL,
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
    """Online-режим: подключается к БД и выполняет миграции асинхронно."""
    connectable = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
