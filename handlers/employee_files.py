"""
Выгрузка файлов из папки сотрудника на Google Drive.
Поток: ввод ИИН/ID → выбор подпапки → бот отправляет файлы.
"""
import logging
from asyncio import to_thread
from html import escape

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import config
from integrations import google_api
from core import keyboards as kb
from core.states import DownloadEmployeeFiles

logger = logging.getLogger(__name__)
router = Router()

# Максимальный размер файла для отправки через Telegram (50 МБ)
MAX_FILE_BYTES = 50 * 1024 * 1024


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "📥 Файлы сотрудника")
async def start_download(message: Message, state: FSMContext) -> None:
    await state.set_state(DownloadEmployeeFiles.waiting_employee)
    await state.update_data(_user_id=message.from_user.id)
    await message.answer(
        "🔍 Введите <b>ИИН</b>, <b>ID</b> или <b>ФИО</b> сотрудника:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск сотрудника, список папок ────────────────────────────────────

@router.message(DownloadEmployeeFiles.waiting_employee)
async def process_dl_employee(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
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
                reply_markup=kb.employee_select_kb(candidates, "dl_emp"),
            )
            return

    await _proceed_dl(message, state, result)


@router.callback_query(lambda c: c.data and c.data.startswith("dl_emp:"))
async def cb_dl_select(call: CallbackQuery, state: FSMContext) -> None:
    part = call.data.split(":")[1]
    if part == "cancel":
        await state.clear()
        await call.message.delete()
        await call.message.answer("Отменено.", reply_markup=menu)
        await call.answer()
        return
    data = await state.get_data()
    candidates = data.get("emp_candidates", [])
    idx = int(part)
    if idx >= len(candidates):
        await call.answer("Ошибка выбора", show_alert=True)
        return
    await call.message.delete()
    await _proceed_dl(call.message, state, candidates[idx])
    await call.answer()


async def _proceed_dl(message: Message, state: FSMContext, result: tuple) -> None:
    data = await state.get_data()
    menu = kb.main_menu(data.get('_user_id', 0))
    _, row_data = result
    full_name  = row_data[config.COL["Полное ФИО"] - 1]
    drive_link = row_data[config.COL["Папка Drive (ссылка)"] - 1]

    if not drive_link:
        await message.answer(
            "⚠️ У сотрудника нет папки на Google Drive.\n"
            "Сначала нажмите «📁 Синхронизировать папки Drive».",
            reply_markup=menu,
        )
        await state.clear()
        return

    folder_id = google_api.extract_folder_id(drive_link)

    await message.answer("⏳ Загружаю список папок...", reply_markup=kb.remove_kb)

    try:
        subfolders = await to_thread(google_api.list_employee_subfolders, folder_id)
    except Exception as e:
        await message.answer(
            f"❌ Ошибка получения папок:\n<code>{escape(str(e))}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )
        await state.clear()
        return

    await state.update_data(full_name=full_name, subfolders=subfolders)
    await state.set_state(DownloadEmployeeFiles.waiting_folder)

    await message.answer(
        f"👤 <b>{escape(full_name)}</b>\n\nВыберите папку для выгрузки:",
        reply_markup=kb.subfolders_kb(subfolders),
        parse_mode="HTML",
    )


# ── Шаг 3 — выбор папки и отправка файлов ─────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("dlfolder:"))
async def process_folder_select(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    idx = int(call.data.split(":")[1])
    data = await state.get_data()
    subfolders = data.get("subfolders", [])
    full_name  = data.get("full_name", "")
    menu = kb.main_menu(data.get('_user_id', 0))

    if idx < 0 or idx >= len(subfolders):
        await call.answer("Папка не найдена", show_alert=True)
        return

    folder = subfolders[idx]
    folder_id   = folder["id"]
    folder_name = folder["name"]

    await call.message.edit_text(
        f"📁 <b>{escape(folder_name)}</b>\n⏳ Получаю список файлов...",
        parse_mode="HTML",
    )
    await call.answer()

    try:
        files = await to_thread(google_api.list_files_in_folder, folder_id)
    except Exception as e:
        await call.message.answer(
            f"❌ Ошибка:\n<code>{escape(str(e))}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )
        await state.clear()
        return

    if not files:
        await call.message.answer(
            f"📭 Папка <b>{escape(folder_name)}</b> пуста.",
            reply_markup=menu,
            parse_mode="HTML",
        )
        await state.clear()
        return

    await call.message.answer(
        f"📁 <b>{escape(folder_name)}</b> — {len(files)} файл(ов)\n"
        f"👤 <b>{escape(full_name)}</b>\n\n⏳ Отправляю...",
        parse_mode="HTML",
    )

    sent   = 0
    skipped = []

    for f in files:
        name      = f["name"]
        file_id   = f["id"]
        mime_type = f["mimeType"]
        size      = int(f.get("size") or 0)
        web_link  = f.get("webViewLink", "")

        # Файл слишком большой — отправляем ссылку
        if size > MAX_FILE_BYTES:
            skipped.append(
                f"• <a href=\"{web_link}\">{escape(name)}</a> "
                f"(>{MAX_FILE_BYTES // 1024 // 1024} МБ — только ссылка)"
            )
            continue

        # Google-native документы помечаем как .pdf
        GOOGLE_NATIVE = {
            "application/vnd.google-apps.document",
            "application/vnd.google-apps.spreadsheet",
            "application/vnd.google-apps.presentation",
        }
        send_name = (name + ".pdf") if mime_type in GOOGLE_NATIVE else name

        try:
            file_bytes = await to_thread(
                google_api.download_file_bytes, file_id, mime_type
            )
            await bot.send_document(
                chat_id=call.message.chat.id,
                document=BufferedInputFile(file_bytes, filename=send_name),
                caption=f"📄 {escape(name)}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception as e:
            logger.warning("Не удалось отправить файл %s: %s", name, e)
            skipped.append(f"• {escape(name)} — ошибка: {escape(str(e))}")

    # Итог
    summary = [f"✅ Отправлено файлов: <b>{sent}</b>"]
    if skipped:
        summary.append(f"\n⚠️ <b>Не удалось отправить ({len(skipped)}):</b>")
        summary.extend(skipped)

    await call.message.answer(
        "\n".join(summary),
        reply_markup=menu,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await state.clear()


@router.callback_query(lambda c: c.data == "dl:cancel")
async def cb_dl_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.delete()
    await call.message.answer("Отменено.", reply_markup=menu)
    await call.answer()
