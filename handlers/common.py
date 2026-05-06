"""Общие команды: /start, отмена из любого состояния."""
from asyncio import to_thread
from html import escape

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from integrations import google_api
from core import keyboards as kb
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"👋 Добро пожаловать, {message.from_user.first_name}!\n"
        "Выберите действие в меню ниже.",
        reply_markup=kb.main_menu(message.from_user.id),
    )


@router.message(StateFilter("*"), lambda m: m.text == "🚫 Отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    menu = kb.main_menu(message.from_user.id)
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного действия.", reply_markup=menu)
        return
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=menu)


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

        menu = kb.main_menu(message.from_user.id)

        # Итоговая строка — всегда отправляем одним сообщением
        summary = (
            f"✅ <b>Создано папок: {len(created)}</b>\n"
            f"📁 Уже было папок: <b>{skipped}</b>"
        )
        if not created:
            summary = f"✅ Новых папок для создания не найдено.\n📁 Уже было папок: <b>{skipped}</b>"
        if errors:
            summary += f"\n❌ <b>Ошибки: {len(errors)}</b>"

        # Детальный список созданных — разбиваем по 50 имён на сообщение
        CHUNK = 50
        for i in range(0, len(created), CHUNK):
            chunk = created[i:i + CHUNK]
            chunk_lines = [f"  • {escape(name)}" for name in chunk]
            part = f"📂 Созданные папки ({i+1}–{i+len(chunk)}):\n" + "\n".join(chunk_lines)
            await message.answer(part, parse_mode="HTML")

        if errors:
            err_lines = [f"  • {escape(e)}" for e in errors]
            await message.answer(
                f"❌ <b>Ошибки ({len(errors)}):</b>\n" + "\n".join(err_lines),
                parse_mode="HTML",
            )

        await message.answer(summary, reply_markup=menu, parse_mode="HTML")
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при синхронизации:\n<code>{escape(str(e))}</code>",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )
