"""Подключение к PostgreSQL через SQLAlchemy async."""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import config

# Движок создаётся один раз при импорте модуля
engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,       # True — логировать все SQL-запросы (удобно при отладке)
    pool_size=5,
    max_overflow=10,
)

# Фабрика сессий — используется во всех сервисах
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
