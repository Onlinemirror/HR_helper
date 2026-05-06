"""Статистика, история документов, ручной запуск уведомлений."""
import logging
from asyncio import to_thread
from html import escape

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from integrations import google_api
from core import keyboards as kb
from core.scheduler import daily_check

logger = logging.getLogger(__name__)
router = Router()


# ── Статистика ────────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "📊 Статистика")
async def show_statistics(message: Message) -> None:
    await message.answer("⏳ Собираю данные...", reply_markup=kb.remove_kb)
    try:
        stats = await to_thread(google_api.get_statistics)

        lines = [f"👥 <b>Активных сотрудников: {stats['total']}</b>\n"]

        lines.append("🏢 <b>По отделам:</b>")
        for dept, cnt in sorted(stats["by_dept"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {escape(dept)}: {cnt}")

        lines.append("\n🏙 <b>По городам:</b>")
        for city, cnt in sorted(stats["by_city"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {escape(city)}: {cnt}")

        lines.append("\n📋 <b>По типу договора:</b>")
        for ctype, cnt in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {escape(ctype)}: {cnt}")

        await message.answer("\n".join(lines), reply_markup=kb.main_menu(message.from_user.id), parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка получения статистики")
        await message.answer(
            f"❌ Ошибка:\n<code>{escape(str(e))}</code>",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )


# ── История документов ─────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "📜 История изменений")
async def start_history(message: Message, state: FSMContext) -> None:
    from core.states import EmployeeCard
    await state.set_state(EmployeeCard.waiting_employee)
    await state.update_data(_history_mode=True)
    await message.answer(
        "🔍 Введите <b>ИИН</b>, <b>ID</b> или <b>ФИО</b> сотрудника:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(lambda m: m.text == "🔔 Запустить проверку уведомлений")
async def manual_notify(message: Message) -> None:
    from aiogram import Bot
    bot: Bot = message.bot
    await message.answer("⏳ Запускаю проверку...", reply_markup=kb.remove_kb)
    try:
        await daily_check(bot)
        await message.answer(
            "✅ Проверка завершена. Уведомления отправлены (если были события).",
            reply_markup=kb.main_menu(message.from_user.id),
        )
    except Exception as e:
        logger.exception("Ошибка ручного запуска проверки")
        await message.answer(
            f"❌ Ошибка:\n<code>{escape(str(e))}</code>",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )


# ── История через карточку сотрудника ─────────────────────────────────────────
# Переопределяем waiting_employee из EmployeeCard для режима истории

@router.message(lambda m: m.text == "📜 История изменений")
async def _history_search(message: Message, state: FSMContext) -> None:
    """Запуск поиска сотрудника для истории."""
    from core.states import EmployeeCard
    await state.set_state(EmployeeCard.waiting_employee)
    await state.update_data(_history_mode=True)
    await message.answer(
        "🔍 Введите <b>ИИН</b>, <b>ID</b> или <b>ФИО</b> сотрудника для просмотра истории:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


async def show_history_for(message: Message, state: FSMContext, result: tuple, menu=None) -> None:
    """Показать историю изменений сотрудника."""
    _, row_data = result
    employee_id = row_data[config.COL["ID"] - 1]
    full_name   = row_data[config.COL["Полное ФИО"] - 1]

    if menu is None:
        data = await state.get_data()
        menu = kb.main_menu(data.get('_user_id', 0))
    await state.clear()
    rows = await to_thread(google_api.get_employee_history, employee_id)

    if not rows:
        await message.answer(
            f"📭 История изменений для <b>{escape(full_name)}</b> пуста.",
            reply_markup=menu,
            parse_mode="HTML",
        )
        return

    lines = [f"📜 <b>История: {escape(full_name)}</b>\n"]
    for r in rows[-20:]:  # последние 20 записей
        date   = escape(r[0]) if len(r) > 0 else "—"
        field  = escape(r[4]) if len(r) > 4 else "—"
        old_v  = escape(r[5]) if len(r) > 5 else "—"
        new_v  = escape(r[6]) if len(r) > 6 else "—"
        author = escape(r[7]) if len(r) > 7 else "—"
        lines.append(f"<b>{date}</b> | {field}: <s>{old_v}</s> → <b>{new_v}</b> ({author})")

    await message.answer(
        "\n".join(lines),
        reply_markup=menu,
        parse_mode="HTML",
    )
