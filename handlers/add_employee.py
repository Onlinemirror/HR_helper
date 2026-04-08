"""FSM-диалог добавления нового сотрудника."""
import asyncio
import logging
from asyncio import to_thread

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

CANCEL = F.text != "🚫 Отмена"

import google_api
import keyboards as kb
from states import AddEmployee

logger = logging.getLogger(__name__)
router = Router()

# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "➕ Добавить сотрудника")
async def start_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.last_name)
    await message.answer("📝 Введите *фамилию* сотрудника:", reply_markup=kb.cancel_kb(),
                         parse_mode="Markdown")


# ── Шаг 2 — Фамилия → Имя ─────────────────────────────────────────────────────

@router.message(AddEmployee.last_name, CANCEL)
async def process_last_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Фамилия не может быть пустой. Попробуйте ещё раз:")
        return
    await state.update_data(last_name=text)
    await state.set_state(AddEmployee.first_name)
    await message.answer("📝 Введите *имя* сотрудника:", parse_mode="Markdown")


# ── Шаг 3 — Имя → Отчество ────────────────────────────────────────────────────

@router.message(AddEmployee.first_name, CANCEL)
async def process_first_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Имя не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(first_name=text)
    await state.set_state(AddEmployee.middle_name)
    await message.answer(
        "📝 Введите *отчество* (или нажмите «Пропустить»):",
        reply_markup=kb.skip_or_cancel_kb(),
        parse_mode="Markdown",
    )


# ── Шаг 4 — Отчество → ИИН ────────────────────────────────────────────────────

@router.message(AddEmployee.middle_name, CANCEL)
async def process_middle_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    middle = "" if text == "Пропустить" else text
    await state.update_data(middle_name=middle)
    await state.set_state(AddEmployee.iin)
    await message.answer(
        "🔢 Введите *ИИН* сотрудника (12 цифр):",
        reply_markup=kb.cancel_kb(),
        parse_mode="Markdown",
    )


# ── Шаг 5 — ИИН → Должность ───────────────────────────────────────────────────

@router.message(AddEmployee.iin, CANCEL)
async def process_iin(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit() or len(text) != 12:
        await message.answer("⚠️ ИИН должен состоять ровно из 12 цифр. Попробуйте ещё раз:")
        return
    # Проверяем уникальность ИИН (в потоке, чтобы не блокировать event loop)
    existing = await to_thread(google_api.find_employee, text)
    if existing:
        _, row = existing
        full_name = row[4]  # Полное ФИО
        await message.answer(
            f"⚠️ Сотрудник с ИИН <b>{text}</b> уже существует: <b>{full_name}</b>.\n"
            "Введите другой ИИН или нажмите «🚫 Отмена».",
            parse_mode="HTML",
        )
        return
    await state.update_data(iin=text)
    await state.set_state(AddEmployee.position)
    await message.answer("💼 Введите *должность* сотрудника:", parse_mode="Markdown")


# ── Шаг 6 — Должность → Город ─────────────────────────────────────────────────

@router.message(AddEmployee.position, CANCEL)
async def process_position(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Должность не может быть пустой. Попробуйте ещё раз:")
        return
    await state.update_data(position=text)
    await state.set_state(AddEmployee.city)
    await message.answer("🏙 Введите *город* сотрудника:", parse_mode="Markdown")


# ── Шаг 7 — Город → Отдел ─────────────────────────────────────────────────────

@router.message(AddEmployee.city, CANCEL)
async def process_city(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Город не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(city=text)
    await state.set_state(AddEmployee.department)
    await message.answer("🏢 Введите *отдел* сотрудника:", parse_mode="Markdown")


# ── Шаг 8 — Отдел → Подтверждение ────────────────────────────────────────────

@router.message(AddEmployee.department, CANCEL)
async def process_department(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Отдел не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(department=text)
    data = await state.get_state()
    await state.set_state(AddEmployee.confirm)

    data = await state.get_data()
    fio = " ".join(filter(None, [data["last_name"], data["first_name"], data.get("middle_name", "")]))
    summary = (
        "📋 <b>Проверьте данные сотрудника:</b>\n\n"
        f"👤 <b>ФИО:</b> {fio}\n"
        f"🔢 <b>ИИН:</b> {data['iin']}\n"
        f"💼 <b>Должность:</b> {data['position']}\n"
        f"🏙 <b>Город:</b> {data['city']}\n"
        f"🏢 <b>Отдел:</b> {data['department']}\n\n"
        "Всё верно?"
    )
    await message.answer(summary, reply_markup=kb.confirm_kb(), parse_mode="HTML")


# ── Шаг 9 — Подтверждение и запись ────────────────────────────────────────────

@router.message(AddEmployee.confirm)
async def process_confirm(message: Message, state: FSMContext) -> None:
    if message.text != "✅ Подтвердить":
        await message.answer("Действие отменено.", reply_markup=kb.main_menu())
        await state.clear()
        return

    data = await state.get_data()
    await message.answer("⏳ Создаю папку на Google Drive и записываю данные...",
                         reply_markup=kb.remove_kb)
    try:
        fio = " ".join(filter(None, [data["last_name"], data["first_name"], data.get("middle_name", "")]))

        # Генерируем ID (в потоке — читает таблицу)
        employee_id = await to_thread(google_api.generate_employee_id, data["city"])

        folder_name = f"{employee_id} {fio}"

        # Создаём папку на Drive (в потоке)
        _, folder_link = await to_thread(
            google_api.create_drive_folder, folder_name, google_api.config.HR_DRIVE_FOLDER_ID
        )

        # Записываем в таблицу (в потоке)
        await to_thread(google_api.add_employee, data, employee_id, folder_link)

        await message.answer(
            f"✅ Сотрудник успешно добавлен!\n\n"
            f"🆔 <b>ID:</b> {employee_id}\n"
            f"👤 <b>ФИО:</b> {fio}\n"
            f"📁 <b>Папка Drive:</b> <a href=\"{folder_link}\">открыть</a>",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка при добавлении сотрудника")
        from html import escape
        await message.answer(
            f"❌ Ошибка при сохранении данных:\n<code>{escape(str(e))}</code>",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
    finally:
        await state.clear()
