"""Карточка сотрудника — просмотр всех данных."""
import logging
from asyncio import to_thread
from html import escape

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from integrations import google_api
from core import keyboards as kb
from core.states import EmployeeCard

logger = logging.getLogger(__name__)
router = Router()


def _format_card(row_data: list[str]) -> str:
    def v(field: str) -> str:
        val = row_data[config.COL[field] - 1]
        return escape(val) if val else "—"

    drive_link = row_data[config.COL["Папка Drive (ссылка)"] - 1]
    drive_part = f'<a href="{drive_link}">открыть</a>' if drive_link else "—"

    return (
        f"👤 <b>{v('Полное ФИО')}</b>\n\n"
        f"🆔 <b>ID:</b> {v('ID')}\n"
        f"🔢 <b>ИИН:</b> {v('ИИН')}\n"
        f"📅 <b>Дата рождения:</b> {v('Дата рождения')}\n\n"
        f"🏙 <b>Город:</b> {v('Город')}\n"
        f"🏢 <b>Отдел:</b> {v('Отдел')}\n"
        f"💼 <b>Должность:</b> {v('Должность')}\n"
        f"👔 <b>Руководитель:</b> {v('Руководитель')}\n\n"
        f"📋 <b>Тип договора:</b> {v('Тип договора')}\n"
        f"📅 <b>Дата приёма:</b> {v('Дата приёма')}\n"
        f"📅 <b>Дата увольнения:</b> {v('Дата увольнения')}\n"
        f"📌 <b>Статус:</b> {v('Статус')}\n\n"
        f"📞 <b>Телефон:</b> {v('Телефон')}\n"
        f"📧 <b>Email:</b> {v('Email')}\n"
        f"🏠 <b>Адрес:</b> {v('Адрес')}\n\n"
        f"📁 <b>Папка Drive:</b> {drive_part}\n"
        f"📝 <b>Примечание:</b> {v('Примечание')}"
    )


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "👤 Карточка сотрудника")
async def start_card(message: Message, state: FSMContext) -> None:
    await state.set_state(EmployeeCard.waiting_employee)
    await state.update_data(_user_id=message.from_user.id)
    await message.answer(
        "🔍 Введите <b>ИИН</b>, <b>ID</b> или <b>ФИО</b> сотрудника:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск ─────────────────────────────────────────────────────────────

@router.message(EmployeeCard.waiting_employee)
async def process_card_query(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        data = await state.get_data()
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(data.get('_user_id', 0)))
        return

    query = message.text.strip()
    result = await to_thread(google_api.find_employee, query)
    if result is None:
        candidates = await to_thread(google_api.find_employees_by_name, query)
        if not candidates:
            await message.answer(
                f"⚠️ Сотрудник <b>{escape(query)}</b> не найден. Попробуйте ещё раз:",
                parse_mode="HTML",
            )
            return
        if len(candidates) == 1:
            result = candidates[0]
        else:
            await state.update_data(emp_candidates=[(idx, row) for idx, row in candidates])
            await message.answer(
                "🔍 Найдено несколько сотрудников. Выберите нужного:",
                reply_markup=kb.employee_select_kb(candidates, "card_emp"),
            )
            return

    await _show_card(message, state, result)


@router.callback_query(lambda c: c.data and c.data.startswith("card_emp:"))
async def cb_card_select(call: CallbackQuery, state: FSMContext) -> None:
    part = call.data.split(":")[1]
    data = await state.get_data()
    if part == "cancel":
        await state.clear()
        await call.message.delete()
        await call.message.answer("Отменено.", reply_markup=kb.main_menu(data.get('_user_id', 0)))
        await call.answer()
        return
    candidates = data.get("emp_candidates", [])
    idx = int(part)
    if idx >= len(candidates):
        await call.answer("Ошибка выбора", show_alert=True)
        return
    await call.message.delete()
    await _show_card(call.message, state, candidates[idx])
    await call.answer()


async def _show_card(message: Message, state: FSMContext, result: tuple) -> None:
    data = await state.get_data()
    history_mode = data.get("_history_mode", False)
    menu = kb.main_menu(data.get('_user_id', 0))

    if history_mode:
        from handlers.statistics import show_history_for
        await show_history_for(message, state, result, menu)
        return

    _, row_data = result
    await state.clear()
    await message.answer(
        _format_card(row_data),
        reply_markup=menu,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
