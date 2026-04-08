"""FSM-диалог загрузки документа в папку сотрудника на Google Drive."""
import logging
from asyncio import to_thread
import os
from pathlib import Path

import aiofiles
from aiogram import Bot, F, Router

CANCEL = F.text != "🚫 Отмена"
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
import google_api
import keyboards as kb
from states import UploadDocument

logger = logging.getLogger(__name__)
router = Router()


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "📄 Загрузить файл")
async def start_upload(message: Message, state: FSMContext) -> None:
    await state.set_state(UploadDocument.waiting_employee_query)
    await message.answer(
        "🔍 Введите <b>ИИН</b> или <b>ID</b> сотрудника, в чью папку нужно загрузить документ:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск сотрудника ──────────────────────────────────────────────────

@router.message(UploadDocument.waiting_employee_query, CANCEL)
async def process_upload_query(message: Message, state: FSMContext) -> None:
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
    drive_link = row_data[config.COL["Папка Drive (ссылка)"] - 1]

    if not drive_link:
        await message.answer(
            "⚠️ У этого сотрудника не указана папка Google Drive.\n"
            "Обратитесь к администратору.",
            reply_markup=kb.main_menu(),
        )
        await state.clear()
        return

    folder_id = google_api.extract_folder_id(drive_link)
    full_name  = row_data[config.COL["Полное ФИО"] - 1]

    await state.update_data(folder_id=folder_id, full_name=full_name)
    await state.set_state(UploadDocument.waiting_file)

    await message.answer(
        f"✅ Сотрудник найден: <b>{full_name}</b>\n\n"
        "📎 Отправьте файл или фото для загрузки в его папку на Drive:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 3 — приём и загрузка файла ───────────────────────────────────────────

@router.message(UploadDocument.waiting_file)
async def process_file(message: Message, state: FSMContext, bot: Bot) -> None:
    # Определяем тип вложения
    document = None
    file_name = None

    if message.document:
        file_id   = message.document.file_id
        file_name = message.document.file_name or f"document_{file_id}"
    elif message.photo:
        photo     = message.photo[-1]   # лучшее качество
        file_id   = photo.file_id
        file_name = f"photo_{file_id}.jpg"
    else:
        await message.answer(
            "⚠️ Пожалуйста, отправьте файл или фото.\n"
            "Другие типы сообщений не поддерживаются."
        )
        return

    data      = await state.get_data()
    folder_id = data["folder_id"]
    full_name = data["full_name"]

    await message.answer(f"⏳ Загружаю <b>{file_name}</b> на Google Drive...",
                         parse_mode="HTML", reply_markup=kb.remove_kb)

    local_path = Path(config.TEMP_DIR) / file_name
    try:
        # Скачиваем файл во временную папку
        await bot.download(file_id, destination=str(local_path))

        # Загружаем на Drive (в потоке)
        file_link = await to_thread(google_api.upload_file_to_drive, str(local_path), file_name, folder_id)

        await message.answer(
            f"✅ Файл <b>{file_name}</b> успешно загружен в папку сотрудника <b>{full_name}</b>!\n\n"
            f"🔗 <a href=\"{file_link}\">Открыть файл на Drive</a>",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка при загрузке файла на Drive")
        from html import escape
        await message.answer(
            f"❌ Ошибка при загрузке файла:\n<code>{escape(str(e))}</code>",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
        )
    finally:
        # Удаляем временный файл в любом случае
        if local_path.exists():
            local_path.unlink()
        await state.clear()
