"""FSM-диалог увольнения сотрудника.

Поток:
  Ввёл ИИН/ID/ФИО
  → Подтвердил увольнение
  → Ввёл дату последнего рабочего дня
  → Принял/ввёл номер приказа
  → Бот генерирует приказ об увольнении (PDF)
  → Запись в таблицу обновляется
"""
import logging
from asyncio import to_thread
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

CANCEL = F.text != "🚫 Отмена"

import config
from integrations import google_api
from core import keyboards as kb
from core.states import FireEmployee

logger = logging.getLogger(__name__)
router = Router()


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "❌ Уволить сотрудника")
async def start_fire(message: Message, state: FSMContext) -> None:
    await state.set_state(FireEmployee.waiting_query)
    await state.update_data(_user_id=message.from_user.id)
    await message.answer(
        "🔍 Введите <b>ИИН</b>, <b>ID</b> или <b>ФИО</b> сотрудника:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск сотрудника ──────────────────────────────────────────────────

@router.message(FireEmployee.waiting_query, CANCEL)
async def process_fire_query(message: Message, state: FSMContext) -> None:
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
                reply_markup=kb.employee_select_kb(candidates, "fire_emp"),
                parse_mode="HTML",
            )
            return

    await _proceed_fire(message, state, result)


@router.callback_query(lambda c: c.data and c.data.startswith("fire_emp:"))
async def cb_fire_select(call: CallbackQuery, state: FSMContext) -> None:
    part = call.data.split(":")[1]
    if part == "cancel":
        data = await state.get_data()
        await state.clear()
        await call.message.delete()
        await call.message.answer("Отменено.", reply_markup=kb.main_menu(data.get("_user_id", 0)))
        await call.answer()
        return
    data = await state.get_data()
    candidates = data.get("emp_candidates", [])
    idx = int(part)
    if idx >= len(candidates):
        await call.answer("Ошибка выбора", show_alert=True)
        return
    await call.message.delete()
    await _proceed_fire(call.message, state, candidates[idx])
    await call.answer()


async def _proceed_fire(message: Message, state: FSMContext, result: tuple) -> None:
    row_index, row_data = result
    current_status = row_data[config.COL["Статус"] - 1]

    if current_status == "Уволен":
        data = await state.get_data()
        await state.clear()
        await message.answer(
            f"⚠️ Сотрудник <b>{escape(row_data[config.COL['Полное ФИО'] - 1])}</b> "
            f"уже имеет статус <b>Уволен</b>.",
            reply_markup=kb.main_menu(data.get("_user_id", 0)),
            parse_mode="HTML",
        )
        return

    await state.update_data(row_index=row_index, row_data=row_data)
    await state.set_state(FireEmployee.confirm)

    full_name  = row_data[config.COL["Полное ФИО"] - 1]
    emp_id     = row_data[config.COL["ID"] - 1]
    department = row_data[config.COL["Отдел"] - 1]
    position   = row_data[config.COL["Должность"] - 1]

    await message.answer(
        f"📋 <b>Найден сотрудник:</b>\n\n"
        f"🆔 <b>ID:</b> {escape(emp_id)}\n"
        f"👤 <b>ФИО:</b> {escape(full_name)}\n"
        f"🏢 <b>Отдел:</b> {escape(department)}\n"
        f"💼 <b>Должность:</b> {escape(position)}\n"
        f"📌 <b>Статус:</b> {escape(current_status)}\n\n"
        "Подтвердите увольнение сотрудника:",
        reply_markup=kb.confirm_kb(),
        parse_mode="HTML",
    )


# ── Шаг 3 — подтверждение ─────────────────────────────────────────────────────

@router.message(FireEmployee.confirm)
async def process_fire_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu = kb.main_menu(data.get("_user_id", 0))

    if message.text != "✅ Подтвердить":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=menu)
        return

    # Переходим к вводу даты увольнения
    await state.set_state(FireEmployee.waiting_date)
    await message.answer(
        "📅 Введите дату последнего рабочего дня (ДД.ММ.ГГГГ):",
        reply_markup=kb.cancel_kb(),
    )


# ── Шаг 4 — дата увольнения ───────────────────────────────────────────────────

@router.message(FireEmployee.waiting_date, CANCEL)
async def process_fire_date(message: Message, state: FSMContext) -> None:
    fire_date = message.text.strip()
    await state.update_data(fire_date=fire_date)

    # Определяем юрлицо сотрудника, чтобы предложить правильный номер приказа
    data = await state.get_data()
    row_data = data["row_data"]
    entity = row_data[config.COL["ЧК/ТОО"] - 1] or "ТОО"
    entity_code = "CHK" if entity == "ЧК" else "TOO"

    suggested = await to_thread(google_api.get_next_prikaz_number, entity)
    await state.update_data(suggested_prikaz_num=suggested, entity=entity, entity_code=entity_code)

    await state.set_state(FireEmployee.waiting_prikaz)
    await message.answer(
        f"📋 <b>Номер приказа об увольнении</b>\n\n"
        f"Следующий по счёту: <code>{suggested}</code>\n\n"
        f"Нажмите <b>✅ Принять</b> — или введите номер вручную:",
        reply_markup=kb.accept_num_kb(),
        parse_mode="HTML",
    )


# ── Шаг 5 — номер приказа и генерация ────────────────────────────────────────

@router.message(FireEmployee.waiting_prikaz, CANCEL)
async def process_fire_prikaz(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu = kb.main_menu(data.get("_user_id", 0))

    # Принимаем предложенный номер или берём введённый вручную
    if message.text.strip() == "✅ Принять":
        prikaz_num = data["suggested_prikaz_num"]
    else:
        prikaz_num = message.text.strip()

    row_index: int      = data["row_index"]
    row_data: list[str] = data["row_data"]
    fire_date: str      = data["fire_date"]
    entity: str         = data["entity"]
    author = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)

    await state.clear()

    # Определяем шаблон приказа по юрлицу сотрудника
    template_name = f"Шаблон_Приказ_увольнение_{entity}"

    await message.answer("⏳ Генерирую приказ об увольнении...", reply_markup=kb.remove_kb)

    try:
        # Генерируем приказ — передаём дату увольнения как доп. переменную
        extra_vars = {"{{ДАТА_ОКОНЧАНИЯ}}": fire_date}
        result = await to_thread(
            google_api.generate_document,
            template_name, entity, row_data, extra_vars, prikaz_num
        )

        nums = result["numbers"]
        num_line = f"\n📋 Номер приказа: <b>{nums['prikaz']}</b>" if nums.get("prikaz") else ""

        await message.answer(
            f"✅ <b>Приказ создан!</b>\n\n"
            f"📁 {escape(result['doc_name'])}"
            + num_line +
            f"\n\n🔗 <a href=\"{result['pdf_url']}\">Открыть PDF</a>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except FileNotFoundError as e:
        await message.answer(
            f"⚠️ Шаблон не найден:\n<code>{escape(str(e))}</code>\n\n"
            "Приказ не создан, но увольнение всё равно будет записано.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка генерации приказа при увольнении")
        await message.answer(
            f"⚠️ Ошибка генерации приказа:\n<code>{escape(str(e))}</code>\n\n"
            "Продолжаем — записываю увольнение в таблицу.",
            parse_mode="HTML",
        )

    # Записываем увольнение в таблицу в любом случае (даже если приказ не создался)
    try:
        await to_thread(google_api.fire_employee, row_index, row_data, author, fire_date)
        full_name = row_data[config.COL["Полное ФИО"] - 1]
        await message.answer(
            f"✅ Сотрудник <b>{escape(full_name)}</b> уволен.\n"
            "Запись добавлена в лог изменений.",
            reply_markup=menu,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка при увольнении сотрудника")
        await message.answer(
            f"❌ Ошибка при обновлении таблицы:\n<code>{escape(str(e))}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )
