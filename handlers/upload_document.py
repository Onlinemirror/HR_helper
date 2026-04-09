"""FSM-диалог загрузки документа в папку сотрудника на Google Drive."""
import logging
from asyncio import to_thread
import os
from pathlib import Path

import aiofiles
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

CANCEL = F.text != "🚫 Отмена"

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
    await state.set_state(UploadDocument.waiting_doc_category)

    await message.answer(
        f"✅ Сотрудник найден: <b>{full_name}</b>\n\n"
        "📁 Выберите категорию документа:",
        reply_markup=kb.remove_kb,
        parse_mode="HTML",
    )
    await message.answer("👇", reply_markup=kb.upload_category_kb(config.UPLOAD_DOC_CATEGORIES))


# ── Шаг 3 — выбор категории (callback) ────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("ucat:"))
async def process_upload_category(call: CallbackQuery, state: FSMContext) -> None:
    idx = int(call.data.split(":")[1])
    if idx < 0 or idx >= len(config.UPLOAD_DOC_CATEGORIES):
        await call.answer("Неизвестная категория", show_alert=True)
        return

    category = config.UPLOAD_DOC_CATEGORIES[idx]
    await state.update_data(doc_category=category)

    await call.message.edit_text(f"📁 Категория: <b>{category}</b>", parse_mode="HTML")
    await call.message.answer(
        "📎 Отправьте файл или фото для загрузки:",
        reply_markup=kb.cancel_kb(),
    )
    await state.set_state(UploadDocument.waiting_file)
    await call.answer()


@router.callback_query(lambda c: c.data == "upload:cancel")
async def cb_upload_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.delete()
    await call.message.answer("Отменено.", reply_markup=kb.main_menu())
    await call.answer()


# ── Шаг 4 — приём и загрузка файла ───────────────────────────────────────────

@router.message(UploadDocument.waiting_file)
async def process_file(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.document:
        file_id   = message.document.file_id
        file_name = message.document.file_name or f"document_{file_id}"
    elif message.photo:
        photo     = message.photo[-1]
        file_id   = photo.file_id
        file_name = f"photo_{file_id}.jpg"
    else:
        await message.answer(
            "⚠️ Пожалуйста, отправьте файл или фото.\n"
            "Другие типы сообщений не поддерживаются."
        )
        return

    data         = await state.get_data()
    folder_id    = data["folder_id"]
    full_name    = data["full_name"]
    doc_category = data.get("doc_category", "Прочее")

    await message.answer(
        f"⏳ Загружаю <b>{file_name}</b> → 📁 <b>{doc_category}</b>...",
        parse_mode="HTML",
        reply_markup=kb.remove_kb,
    )

    local_path = Path(config.TEMP_DIR) / file_name
    try:
        # Скачиваем во временную папку
        await bot.download(file_id, destination=str(local_path))

        # Находим/создаём подпапку категории внутри папки сотрудника
        subfolder_id = await to_thread(
            google_api.get_or_create_subfolder, folder_id, doc_category
        )

        # Загружаем файл в подпапку
        file_link = await to_thread(
            google_api.upload_file_to_drive, str(local_path), file_name, subfolder_id
        )

        await message.answer(
            f"✅ <b>{file_name}</b> загружен!\n\n"
            f"👤 Сотрудник: <b>{full_name}</b>\n"
            f"📁 Папка: <b>{doc_category}</b>\n\n"
            f"🔗 <a href=\"{file_link}\">Открыть файл на Drive</a>",
            reply_markup=kb.main_menu(),
            parse_mode="HTML",
            disable_web_page_preview=True,
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
        if local_path.exists():
            local_path.unlink()
        await state.clear()
