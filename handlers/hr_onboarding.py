"""
HR-команды онбординга.

Добавить новичка:  кнопка «🎓 Добавить новичка» → FSM-диалог
Список новичков:   кнопка «📋 Список новичков»
Прогресс:          кнопка «📊 Прогресс новичка» → ввод ID → детали
"""
import logging
from datetime import datetime
from html import escape

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from core import keyboards as kb
from core import user_store
from core.states import HRAddOnboarding, HRProgressQuery
from models.db import AsyncSessionFactory
from services import onboarding as svc

logger = logging.getLogger(__name__)
router = Router()

_DATE_FMT = "%d.%m.%Y"


def _hr_or_admin(message: Message) -> bool:
    uid = message.from_user.id
    return user_store.is_admin(uid) or user_store.is_hr(uid)


# ── Добавить новичка ──────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "🎓 Добавить новичка")
async def start_add_onboarding(message: Message, state: FSMContext) -> None:
    if not _hr_or_admin(message):
        await message.answer("⛔ Только для HR и администраторов.")
        return

    await state.set_state(HRAddOnboarding.telegram_id)
    await message.answer(
        "🎓 <b>Добавление сотрудника на онбординг</b>\n\n"
        "Шаг 1/6. Введите <b>Telegram ID</b> сотрудника:\n\n"
        "💡 Сотрудник может узнать свой ID командой /myid",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(HRAddOnboarding.telegram_id)
async def step_telegram_id(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ ID должен быть числом. Попробуйте ещё раз:")
        return

    telegram_id = int(text)

    # Проверяем — нет ли уже такого сотрудника в онбординге
    async with AsyncSessionFactory() as session:
        exists = await svc.employee_exists(session, telegram_id)
    if exists:
        await message.answer(
            f"⚠️ Сотрудник с ID <code>{telegram_id}</code> уже есть в системе онбординга.\n"
            "Введите другой ID или нажмите «🚫 Отмена».",
            parse_mode="HTML",
        )
        return

    # Пробуем подтянуть имя из Telegram
    prefill_name = ""
    try:
        chat = await message.bot.get_chat(telegram_id)
        parts = [p for p in [chat.first_name, chat.last_name] if p]
        prefill_name = " ".join(parts)
    except Exception:
        pass

    await state.update_data(telegram_id=telegram_id)
    await state.set_state(HRAddOnboarding.full_name)

    if prefill_name:
        await message.answer(
            f"Шаг 2/6. Имя из Telegram: <b>{escape(prefill_name)}</b>\n\n"
            "Введите ФИО полностью (Фамилия Имя Отчество) или нажмите «Принять» чтобы оставить как есть.",
            reply_markup=kb.accept_num_kb(),
            parse_mode="HTML",
        )
        await state.update_data(_prefill_name=prefill_name)
    else:
        await message.answer(
            "Шаг 2/6. Введите <b>ФИО</b> сотрудника (Фамилия Имя Отчество):",
            reply_markup=kb.cancel_kb(),
            parse_mode="HTML",
        )


@router.message(HRAddOnboarding.full_name)
async def step_full_name(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    data = await state.get_data()
    if message.text == "✅ Принять":
        full_name = data.get("_prefill_name", "")
    else:
        full_name = message.text.strip()

    if not full_name:
        await message.answer("⚠️ ФИО не может быть пустым. Введите ФИО:")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(HRAddOnboarding.position)
    await message.answer(
        "Шаг 3/6. Введите <b>должность</b> (или «Пропустить»):",
        reply_markup=kb.skip_or_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(HRAddOnboarding.position)
async def step_position(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    position = None if message.text == "Пропустить" else message.text.strip()
    await state.update_data(position=position)
    await state.set_state(HRAddOnboarding.department)
    await message.answer(
        "Шаг 4/6. Введите <b>отдел</b> (или «Пропустить»):",
        reply_markup=kb.skip_or_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(HRAddOnboarding.department)
async def step_department(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    department = None if message.text == "Пропустить" else message.text.strip()
    await state.update_data(department=department)
    await state.set_state(HRAddOnboarding.hr_sheet_id)
    await message.answer(
        "Шаг 5/6. Введите <b>ID сотрудника из Google Sheets</b> (напр. ALA-001) "
        "или «Пропустить»:",
        reply_markup=kb.skip_or_cancel_kb(),
        parse_mode="HTML",
    )


@router.message(HRAddOnboarding.hr_sheet_id)
async def step_hr_sheet_id(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    hr_sheet_id = None if message.text == "Пропустить" else message.text.strip()
    await state.update_data(hr_sheet_id=hr_sheet_id)
    await state.set_state(HRAddOnboarding.start_date)
    await message.answer(
        "Шаг 6/6. Введите <b>дату первого рабочего дня</b> (ДД.ММ.ГГГГ):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(HRAddOnboarding.start_date)
async def step_start_date(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    try:
        start_date = datetime.strptime(message.text.strip(), _DATE_FMT)
    except ValueError:
        await message.answer("⚠️ Неверный формат. Введите дату как ДД.ММ.ГГГГ:")
        return

    await state.update_data(start_date=start_date)
    await state.set_state(HRAddOnboarding.confirm)

    data = await state.get_data()
    lines = [
        "📋 <b>Проверьте данные:</b>\n",
        f"👤 ФИО:           {escape(data['full_name'])}",
        f"🆔 Telegram ID:   <code>{data['telegram_id']}</code>",
        f"💼 Должность:     {escape(data['position'] or '—')}",
        f"🏢 Отдел:         {escape(data['department'] or '—')}",
        f"🗂 ID в таблице:  {escape(data['hr_sheet_id'] or '—')}",
        f"📅 Дата выхода:   {start_date.strftime(_DATE_FMT)}",
    ]
    await message.answer(
        "\n".join(lines),
        reply_markup=kb.confirm_kb(),
        parse_mode="HTML",
    )


@router.message(HRAddOnboarding.confirm)
async def step_confirm(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    if message.text != "✅ Подтвердить":
        await message.answer("Нажмите «✅ Подтвердить» или «🚫 Отмена».")
        return

    data = await state.get_data()
    await state.clear()

    async with AsyncSessionFactory() as session:
        # Шаблон не выбираем пока их нет — template_id=None
        templates = await svc.get_templates(session)
        template_id = templates[0].id if templates else None

        employee = await svc.create_employee(
            session,
            telegram_id=data["telegram_id"],
            full_name=data["full_name"],
            position=data.get("position"),
            department=data.get("department"),
            hr_sheet_id=data.get("hr_sheet_id"),
            start_date=data["start_date"],
            template_id=template_id,
        )

    await message.answer(
        f"✅ <b>{escape(employee.full_name)}</b> добавлен на онбординг.\n"
        f"🆔 ID в системе: <code>{employee.id}</code>\n"
        f"📅 Дата выхода: {employee.start_date.strftime(_DATE_FMT)}",
        reply_markup=kb.main_menu(message.from_user.id),
        parse_mode="HTML",
    )

    # Уведомляем сотрудника если он уже писал боту
    try:
        await message.bot.send_message(
            employee.telegram_id,
            f"👋 <b>Добро пожаловать, {escape(employee.full_name)}!</b>\n\n"
            f"Вы зарегистрированы в системе онбординга.\n"
            f"Дата первого рабочего дня: <b>{employee.start_date.strftime(_DATE_FMT)}</b>\n\n"
            "Скоро вы начнёте получать задачи для прохождения адаптации.",
            parse_mode="HTML",
        )
    except Exception:
        # Сотрудник ещё не писал боту — ничего страшного
        pass


# ── Список новичков ───────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "📋 Список новичков")
async def list_onboarding(message: Message) -> None:
    if not _hr_or_admin(message):
        await message.answer("⛔ Только для HR и администраторов.")
        return

    async with AsyncSessionFactory() as session:
        employees = await svc.get_active_employees(session)
        if not employees:
            await message.answer(
                "📋 Нет активных сотрудников на онбординге.\n\n"
                "Добавьте новичка кнопкой «🎓 Добавить новичка».",
                reply_markup=kb.main_menu(message.from_user.id),
            )
            return

        # Подгружаем прогресс для каждого
        progress = {}
        for emp in employees:
            progress[emp.id] = await svc.get_employee_progress(session, emp.id)

    lines = [f"📋 <b>Онбординг — активных: {len(employees)}</b>\n"]
    for emp in employees:
        p = progress[emp.id]
        days_in = (datetime.now() - emp.start_date).days
        template_name = emp.template.name if emp.template else "без шаблона"

        if p["total"]:
            prog_str = f"{p['done']}/{p['total']} ({p['percent']}%)"
        else:
            prog_str = "задачи не назначены"

        lines.append(
            f"• <b>{escape(emp.full_name)}</b>\n"
            f"  🆔 <code>{emp.id}</code> | 📅 {emp.start_date.strftime(_DATE_FMT)} "
            f"(день {days_in}) | 📊 {prog_str}\n"
            f"  📁 {escape(template_name)}"
        )

    await message.answer(
        "\n".join(lines),
        reply_markup=kb.main_menu(message.from_user.id),
        parse_mode="HTML",
    )
