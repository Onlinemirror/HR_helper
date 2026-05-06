"""
Модели онбординга.

Employee         — сотрудник на онбординге (привязан к Telegram ID)
ChecklistTemplate — шаблон чеклиста (набор задач по должности/отделу)
Task             — задача из шаблона (триггер в днях от даты выхода)
EmployeeTask     — конкретная задача для конкретного сотрудника (статус, даты)
"""
import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TaskStatus(enum.Enum):
    pending   = "pending"    # задача ещё не отправлена
    sent      = "sent"       # отправлена, ждём выполнения
    done      = "done"       # сотрудник отметил выполненной
    skipped   = "skipped"    # пропущена вручную HR


class ChecklistTemplate(Base):
    """Шаблон чеклиста — набор задач, привязанный к должности или отделу."""
    __tablename__ = "checklist_templates"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True)
    name:        Mapped[str] = mapped_column(String(255), nullable=False)  # напр. "Разработчик"
    description: Mapped[str | None] = mapped_column(Text)

    tasks:     Mapped[list["Task"]]     = relationship(back_populates="template", cascade="all, delete-orphan")
    employees: Mapped[list["Employee"]] = relationship(back_populates="template")


class Task(Base):
    """Задача внутри шаблона. trigger_days — через сколько дней от start_date отправить."""
    __tablename__ = "tasks"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id:  Mapped[int] = mapped_column(ForeignKey("checklist_templates.id"), nullable=False)
    block_name:   Mapped[str] = mapped_column(String(100), nullable=False)  # day1 / week1 / month1 / ...
    trigger_days: Mapped[int] = mapped_column(Integer, nullable=False)       # 0, 7, 30, 60, 90
    title:        Mapped[str] = mapped_column(String(500), nullable=False)
    description:  Mapped[str | None] = mapped_column(Text)
    link:         Mapped[str | None] = mapped_column(Text)                   # ссылка на инструкцию / форму
    sort_order:   Mapped[int] = mapped_column(Integer, default=0)

    template:        Mapped["ChecklistTemplate"]  = relationship(back_populates="tasks")
    employee_tasks:  Mapped[list["EmployeeTask"]] = relationship(back_populates="task")


class Employee(Base):
    """Сотрудник на онбординге. Создаётся когда HR подтверждает регистрацию."""
    __tablename__ = "employees"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int]      = mapped_column(BigInteger, unique=True, nullable=False)
    full_name:   Mapped[str]      = mapped_column(String(255), nullable=False)
    position:    Mapped[str | None] = mapped_column(String(255))   # должность
    department:  Mapped[str | None] = mapped_column(String(255))   # отдел
    # ID сотрудника из Google Sheets (напр. ALA-001) — для связи двух систем
    hr_sheet_id: Mapped[str | None] = mapped_column(String(50))
    start_date:  Mapped[datetime]   = mapped_column(DateTime(timezone=False), nullable=False)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("checklist_templates.id"))
    is_active:   Mapped[bool]       = mapped_column(Boolean, default=True)
    created_at:  Mapped[datetime]   = mapped_column(DateTime, server_default=func.now())

    template:        Mapped["ChecklistTemplate | None"] = relationship(back_populates="employees")
    employee_tasks:  Mapped[list["EmployeeTask"]]       = relationship(back_populates="employee", cascade="all, delete-orphan")


class EmployeeTask(Base):
    """Конкретная задача назначенная сотруднику — со статусом и датами."""
    __tablename__ = "employee_tasks"

    id:             Mapped[int]           = mapped_column(Integer, primary_key=True)
    employee_id:    Mapped[int]           = mapped_column(ForeignKey("employees.id"), nullable=False)
    task_id:        Mapped[int]           = mapped_column(ForeignKey("tasks.id"), nullable=False)
    status:         Mapped[TaskStatus]    = mapped_column(Enum(TaskStatus), default=TaskStatus.pending, nullable=False)
    sent_at:        Mapped[datetime|None] = mapped_column(DateTime)         # когда отправлена сотруднику
    completed_at:   Mapped[datetime|None] = mapped_column(DateTime)         # когда отмечена выполненной
    reminder_count: Mapped[int]           = mapped_column(Integer, default=0)  # сколько напоминаний отправлено

    employee: Mapped["Employee"] = relationship(back_populates="employee_tasks")
    task:     Mapped["Task"]     = relationship(back_populates="employee_tasks")
