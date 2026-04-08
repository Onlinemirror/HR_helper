"""FSM-диалог увольнения сотрудника."""
import logging
from asyncio import to_thread

from aiogram import F, Router

CANCEL = F.text != "🚫 Отмена"
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import google_api
import keyboards as kb
from states import FireEmployee

logger = logging.getLogger(__name__)
router = Router()


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "❌ Уволить сотрудника")
async def start_fire(message: Message, state: FSMContext) -> None:
    await state.set_state(FireEmployee.waiting_query)
    await message.answer(
        "🔍 Введите <b>ИИН</b> или <b>ID</b> сотрудника для увольнения:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск сотрудника ──────────────────────────────────────────────────

@router.message(FireEmployee.waiting_query, CANCEL)
async def process_fire_query(message: Message, state: FSMContext) -> None:
    query = message.text.strip()

    result = await to_thread(google_api.find_employee, query)
    if result is None:
        await message.answer(
            f"⚠️ Сотрудник с ИИН/ID <b>{query}</b> не найден.\n"
            "Проверьте данные и попробуйте ещё раз:",
            parse_mode="HTML",
        )
        return

    row_index, row_data = result
    import config
    current_status = row_data[config.COL["Статус"] - 1]

    if current_status == "Уволен":
        await message.answer(
            f"⚠️ Сотрудник <b>{row_data[config.COL['Полное ФИО'] - 1]}</b> "
            f"уже имеет статус <b>Уволен</b>.",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
        await state.clear()
        return

    await state.update_data(row_index=row_index, row_data=row_data)
    await state.set_state(FireEmployee.confirm)

    full_name  = row_data[config.COL["Полное ФИО"] - 1]
    emp_id     = row_data[config.COL["ID"] - 1]
    department = row_data[config.COL["Отдел"] - 1]
    position   = row_data[config.COL["Должность"] - 1]

    await message.answer(
        f"📋 <b>Найден сотрудник:</b>\n\n"
        f"🆔 <b>ID:</b> {emp_id}\n"
        f"👤 <b>ФИО:</b> {full_name}\n"
        f"🏢 <b>Отдел:</b> {department}\n"
        f"💼 <b>Должность:</b> {position}\n"
        f"📌 <b>Статус:</b> {current_status}\n\n"
        "Подтвердите увольнение сотрудника:",
        reply_markup=kb.confirm_kb(),
        parse_mode="HTML",
    )


# ── Шаг 3 — подтверждение и запись ────────────────────────────────────────────

@router.message(FireEmployee.confirm)
async def process_fire_confirm(message: Message, state: FSMContext) -> None:
    if message.text != "✅ Подтвердить":
        await message.answer("Действие отменено.", reply_markup=kb.main_menu())
        await state.clear()
        return

    data = await state.get_data()
    row_index: int      = data["row_index"]
    row_data: list[str] = data["row_data"]

    author = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)

    try:
        await to_thread(google_api.fire_employee, row_index, row_data, author)

        import config
        full_name = row_data[config.COL["Полное ФИО"] - 1]
        await message.answer(
            f"✅ Сотрудник <b>{full_name}</b> успешно уволен.\n"
            "Запись добавлена в лог изменений.",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка при увольнении сотрудника")
        from html import escape
        await message.answer(
            f"❌ Ошибка при обновлении данных:\n<code>{escape(str(e))}</code>",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
    finally:
        await state.clear()
