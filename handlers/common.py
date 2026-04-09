"""Общие команды: /start, отмена из любого состояния."""
from asyncio import to_thread
from html import escape

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import google_api
import keyboards as kb

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"👋 Добро пожаловать, {message.from_user.first_name}!\n"
        "Выберите действие в меню ниже.",
        reply_markup=kb.main_menu(),
    )


@router.message(StateFilter("*"), lambda m: m.text == "🚫 Отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного действия.", reply_markup=kb.main_menu())
        return
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=kb.main_menu())


@router.message(lambda m: m.text == "📁 Синхронизировать папки Drive")
async def sync_drive(message: Message) -> None:
    await message.answer(
        "⏳ Проверяю папки сотрудников на Google Drive...\n"
        "Это может занять некоторое время.",
        reply_markup=kb.remove_kb,
    )
    try:
        result = await to_thread(google_api.sync_drive_folders)

        created = result["created"]
        skipped = result["skipped"]
        errors  = result["errors"]

        lines = []

        if created:
            lines.append(f"✅ <b>Создано папок: {len(created)}</b>")
            for name in created:
                lines.append(f"  • {escape(name)}")
        else:
            lines.append("✅ Новых папок для создания не найдено.")

        lines.append(f"\n📁 Уже было папок: <b>{skipped}</b>")

        if errors:
            lines.append(f"\n❌ <b>Ошибки ({len(errors)}):</b>")
            for err in errors:
                lines.append(f"  • {escape(err)}")

        await message.answer(
            "\n".join(lines),
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при синхронизации:\n<code>{escape(str(e))}</code>",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
