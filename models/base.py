"""Базовый класс для всех SQLAlchemy-моделей."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
