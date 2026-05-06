"""
Бизнес-логика онбординга.
Все функции принимают AsyncSession и работают только с БД.
"""
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.onboarding import ChecklistTemplate, Employee, EmployeeTask, Task, TaskStatus


async def create_employee(
    session: AsyncSession,
    *,
    telegram_id: int,
    full_name: str,
    position: str | None,
    department: str | None,
    hr_sheet_id: str | None,
    start_date: datetime,
    template_id: int | None = None,
) -> Employee:
    """Создать сотрудника и сразу назначить задачи из шаблона (если шаблон есть)."""
    employee = Employee(
        telegram_id=telegram_id,
        full_name=full_name,
        position=position,
        department=department,
        hr_sheet_id=hr_sheet_id,
        start_date=start_date,
        template_id=template_id,
        is_active=True,
    )
    session.add(employee)
    await session.flush()  # получаем employee.id до commit

    # Назначаем задачи из шаблона
    if template_id:
        tasks = (await session.execute(
            select(Task).where(Task.template_id == template_id).order_by(Task.sort_order)
        )).scalars().all()
        for task in tasks:
            session.add(EmployeeTask(
                employee_id=employee.id,
                task_id=task.id,
                status=TaskStatus.pending,
            ))

    await session.commit()
    return employee


async def get_active_employees(session: AsyncSession) -> list[Employee]:
    """Все активные сотрудники на онбординге, от новых к старым."""
    result = await session.execute(
        select(Employee)
        .where(Employee.is_active.is_(True))
        .options(selectinload(Employee.template))
        .order_by(Employee.start_date.desc())
    )
    return result.scalars().all()


async def get_employee_by_id(session: AsyncSession, employee_id: int) -> Employee | None:
    result = await session.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(
            selectinload(Employee.employee_tasks).selectinload(EmployeeTask.task)
        )
    )
    return result.scalar_one_or_none()


async def get_employee_by_telegram_id(session: AsyncSession, telegram_id: int) -> Employee | None:
    result = await session.execute(
        select(Employee).where(Employee.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def employee_exists(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(
        select(func.count()).select_from(Employee).where(
            Employee.telegram_id == telegram_id,
            Employee.is_active.is_(True),
        )
    )
    return (result.scalar() or 0) > 0


async def get_employee_progress(session: AsyncSession, employee_id: int) -> dict:
    """Статистика по задачам: total, done, percent."""
    total = (await session.execute(
        select(func.count()).select_from(EmployeeTask)
        .where(EmployeeTask.employee_id == employee_id)
    )).scalar() or 0

    done = (await session.execute(
        select(func.count()).select_from(EmployeeTask)
        .where(
            EmployeeTask.employee_id == employee_id,
            EmployeeTask.status == TaskStatus.done,
        )
    )).scalar() or 0

    return {
        "total": total,
        "done": done,
        "percent": int(done / total * 100) if total else 0,
    }


async def get_templates(session: AsyncSession) -> list[ChecklistTemplate]:
    result = await session.execute(
        select(ChecklistTemplate).order_by(ChecklistTemplate.name)
    )
    return result.scalars().all()


async def deactivate_employee(session: AsyncSession, employee_id: int) -> bool:
    """Завершить онбординг сотрудника (is_active = False)."""
    emp = await get_employee_by_id(session, employee_id)
    if not emp:
        return False
    emp.is_active = False
    await session.commit()
    return True
