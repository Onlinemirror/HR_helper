"""FSM-диалог редактирования данных сотрудника."""
import logging
from asyncio import to_thread
from html import escape

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from integrations import google_api
from core import keyboards as kb
from core.states import EditEmployee

logger = logging.getLogger(__name__)
router = Router()


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "✏️ Редактировать сотрудника")
async def start_edit(message: Message, state: FSMContext) -> None:
    await state.set_state(EditEmployee.waiting_employee)
    await state.update_data(_user_id=message.from_user.id)
    await message.answer(
        "🔍 Введите <b>ИИН</b>, <b>ID</b> или <b>ФИО</b> сотрудника:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск сотрудника ──────────────────────────────────────────────────

@router.message(EditEmployee.waiting_employee)
async def process_edit_query(message: Message, state: FSMContext) -> None:
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
                reply_markup=kb.employee_select_kb(candidates, "edit_emp"),
            )
            return

    await _show_field_select(message, state, result)


@router.callback_query(lambda c: c.data and c.data.startswith("edit_emp:"))
async def cb_edit_select(call: CallbackQuery, state: FSMContext) -> None:
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
    await _show_field_select(call.message, state, candidates[idx])
    await call.answer()


async def _show_field_select(message: Message, state: FSMContext, result: tuple) -> None:
    row_index, row_data = result
    full_name = row_data[config.COL["Полное ФИО"] - 1]
    await state.update_data(row_index=row_index, row_data=row_data)
    await state.set_state(EditEmployee.waiting_field)
    await message.answer(
        f"👤 <b>{escape(full_name)}</b>\n\nВыберите поле для редактирования:",
        reply_markup=kb.remove_kb,
        parse_mode="HTML",
    )
    await message.answer("👇", reply_markup=kb.edit_fields_kb())


# ── Шаг 3 — выбор поля ────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("editf:"))
async def process_field_select(call: CallbackQuery, state: FSMContext) -> None:
    field = call.data.split(":", 1)[1]
    if field not in config.COL:
        await call.answer("Неизвестное поле", show_alert=True)
        return

    data = await state.get_data()
    row_data = data["row_data"]
    current_val = row_data[config.COL[field] - 1] or "—"

    await state.update_data(edit_field=field)
    await state.set_state(EditEmployee.waiting_value)
    await call.message.edit_text(
        f"✏️ <b>{escape(field)}</b>\n\nТекущее значение: <code>{escape(current_val)}</code>\n\n"
        "Введите новое значение:",
        parse_mode="HTML",
    )
    await call.message.answer("(или нажмите «🚫 Отмена»)", reply_markup=kb.cancel_kb())
    await call.answer()


@router.callback_query(lambda c: c.data == "edit:cancel")
async def cb_edit_cancel(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    menu = kb.main_menu(data.get('_user_id', 0))
    await state.clear()
    await call.message.delete()
    await call.message.answer("Отменено.", reply_markup=menu)
    await call.answer()


# ── Шаг 4 — ввод нового значения ──────────────────────────────────────────────

@router.message(EditEmployee.waiting_value)
async def process_new_value(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        data = await state.get_data()
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(data.get('_user_id', 0)))
        return

    new_value = message.text.strip()
    data = await state.get_data()
    field    = data["edit_field"]
    row_data = data["row_data"]
    full_name = row_data[config.COL["Полное ФИО"] - 1]
    old_value = row_data[config.COL[field] - 1] or "—"

    await state.update_data(new_value=new_value)
    await state.set_state(EditEmployee.confirm)
    await message.answer(
        f"👤 <b>{escape(full_name)}</b>\n\n"
        f"📝 Поле: <b>{escape(field)}</b>\n"
        f"Было: <code>{escape(old_value)}</code>\n"
        f"Станет: <code>{escape(new_value)}</code>\n\n"
        "Подтвердить изменение?",
        reply_markup=kb.confirm_kb(),
        parse_mode="HTML",
    )


# ── Шаг 5 — подтверждение и запись ────────────────────────────────────────────

@router.message(EditEmployee.confirm)
async def process_edit_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu = kb.main_menu(data.get('_user_id', 0))
    # Очищаем state сразу — повторные нажатия уже не попадут в этот хендлер
    await state.clear()
    if message.text != "✅ Подтвердить":
        await message.answer("Отменено.", reply_markup=menu)
        return
    row_index = data["row_index"]
    row_data  = data["row_data"]
    field     = data["edit_field"]
    new_value = data["new_value"]
    author = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)

    try:
        await to_thread(google_api.update_employee_field, row_index, row_data, field, new_value, author)
        full_name = row_data[config.COL["Полное ФИО"] - 1]
        await message.answer(
            f"✅ Данные сотрудника <b>{escape(full_name)}</b> обновлены.\n"
            f"Поле <b>{escape(field)}</b> → <code>{escape(new_value)}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка при редактировании сотрудника")
        await message.answer(
            f"❌ Ошибка:\n<code>{escape(str(e))}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )
