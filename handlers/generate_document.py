"""
FSM генерации документа из шаблона Google Docs.

Поток:
  Нажал «📋 Создать документ»
  → Ввёл ИИН/ID сотрудника
  → Выбрал категорию + юрлицо (inline)
  → Выбрал тип документа (inline)
  → Ввёл доп. данные (если нужны) — по одному полю за раз
  → Подтвердил → бот генерирует PDF
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
from core.states import GenerateDocument


def _is_prikaz(template_name: str) -> bool:
    return "приказ" in template_name.lower()

logger = logging.getLogger(__name__)
router = Router()

CRITERIA_LABELS = {
    "quality":       "Качество работы",
    "teamwork":      "Командная работа",
    "initiative":    "Инициативность",
    "communication": "Коммуникация",
    "knowledge":     "Проф. знания",
}


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "📋 Создать документ")
async def start_generate(message: Message, state: FSMContext) -> None:
    await state.set_state(GenerateDocument.waiting_employee)
    await state.update_data(_user_id=message.from_user.id)
    await message.answer(
        "🔍 Введите <b>ИИН</b>, <b>ID</b> или <b>ФИО</b> сотрудника:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск сотрудника ──────────────────────────────────────────────────

@router.message(GenerateDocument.waiting_employee, CANCEL)
async def process_employee(message: Message, state: FSMContext) -> None:
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
                reply_markup=kb.employee_select_kb(candidates, "gen_emp"),
            )
            return

    await _proceed_generate(message, state, result)


@router.callback_query(lambda c: c.data and c.data.startswith("gen_emp:"))
async def cb_gen_select(call: CallbackQuery, state: FSMContext) -> None:
    part = call.data.split(":")[1]
    if part == "cancel":
        await state.clear()
        await call.message.delete()
        await call.message.answer("Отменено.", reply_markup=kb.main_menu(call.from_user.id))
        await call.answer()
        return
    data = await state.get_data()
    candidates = data.get("emp_candidates", [])
    idx = int(part)
    if idx >= len(candidates):
        await call.answer("Ошибка выбора", show_alert=True)
        return
    await call.message.delete()
    await _proceed_generate(call.message, state, candidates[idx])
    await call.answer()


async def _proceed_generate(message: Message, state: FSMContext, result: tuple) -> None:
    row_index, row_data = result
    await state.update_data(row_index=row_index, row_data=row_data)

    full_name = row_data[config.COL["Полное ФИО"] - 1]
    position  = row_data[config.COL["Должность"] - 1]
    await message.answer(
        f"✅ Найден: <b>{escape(full_name)}</b> — {escape(position)}\n\n"
        "Выберите тип документа:",
        reply_markup=kb.remove_kb,
        parse_mode="HTML",
    )
    await message.answer("👇", reply_markup=kb.doc_category_kb())


# ── Шаг 3 — выбор категории + юрлица (callback) ──────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("cat:"))
async def process_category(call: CallbackQuery, state: FSMContext) -> None:
    parts        = call.data.split(":")  # cat:prikaz:TOO
    category     = parts[1]
    entity_code  = parts[2] if len(parts) > 2 else ""
    entity_label = {"TOO": "ТОО", "CHK": "ЧК"}.get(entity_code, "")

    await state.update_data(category=category, entity=entity_label, entity_code=entity_code, prikaz_num=None)
    await call.message.edit_text(
        f"📄 Выберите документ ({entity_label or 'без юрлица'}):",
        reply_markup=kb.doc_type_kb(category, entity_code),
    )
    await call.answer()


# ── Шаг 4 — выбор конкретного документа (callback dt:N) ──────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("dt:"))
async def process_doc_type(call: CallbackQuery, state: FSMContext) -> None:
    idx = int(call.data.split(":")[1])
    template_name = kb.template_by_index(idx)
    if not template_name:
        await call.answer("Неизвестный тип документа", show_alert=True)
        return
    await state.update_data(template_name=template_name)

    # Определяем нужные доп. поля
    extra_fields = config.EXTRA_FIELDS.get(template_name, [])
    await state.update_data(
        extra_fields=extra_fields,
        extra_fields_idx=0,
        collected_extra={},
    )

    await call.message.delete()

    # Для приказов — спрашиваем номер (с авто-подсказкой)
    if _is_prikaz(template_name):
        data = await state.get_data()
        entity_code = data.get("entity_code", "")
        entity = {"TOO": "ТОО", "CHK": "ЧК"}.get(entity_code, "ЧК")
        suggested = await to_thread(google_api.get_next_prikaz_number, entity)
        await state.update_data(suggested_prikaz_num=suggested)
        await call.message.answer(
            f"📋 <b>Номер приказа</b>\n\n"
            f"Следующий по счёту: <code>{suggested}</code>\n\n"
            f"Нажмите <b>✅ Принять</b> — или введите номер вручную:",
            reply_markup=kb.accept_num_kb(),
            parse_mode="HTML",
        )
        await state.set_state(GenerateDocument.waiting_prikaz_num)
    elif extra_fields:
        _, prompt, _ = extra_fields[0]
        await call.message.answer(prompt, reply_markup=kb.cancel_kb())
        await state.set_state(GenerateDocument.waiting_extra)
    else:
        await _show_confirm(call.message, state)

    await call.answer()


# ── Шаг 5а — ввод/подтверждение номера приказа ────────────────────────────────

@router.message(GenerateDocument.waiting_prikaz_num, CANCEL)
async def process_prikaz_num(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    suggested = data.get("suggested_prikaz_num", "")

    if message.text.strip() == "✅ Принять":
        prikaz_num = suggested
    else:
        prikaz_num = message.text.strip()

    await state.update_data(prikaz_num=prikaz_num)

    # Переходим к доп. полям или сразу к подтверждению
    extra_fields = data.get("extra_fields", [])
    if extra_fields:
        _, prompt, _ = extra_fields[0]
        await message.answer(prompt, reply_markup=kb.cancel_kb())
        await state.set_state(GenerateDocument.waiting_extra)
    else:
        await _show_confirm(message, state)


# ── Шаг 5 — сбор доп. полей ───────────────────────────────────────────────────

@router.message(GenerateDocument.waiting_extra, CANCEL)
async def process_extra_field(message: Message, state: FSMContext) -> None:
    data      = await state.get_data()
    fields    = data["extra_fields"]
    idx       = data["extra_fields_idx"]
    collected = data["collected_extra"]

    field_key, _, _ = fields[idx]
    collected[field_key] = message.text.strip()
    idx += 1

    await state.update_data(extra_fields_idx=idx, collected_extra=collected)

    if idx < len(fields):
        # Следующее поле
        _, prompt, _ = fields[idx]
        await message.answer(prompt)
    else:
        # Все поля собраны — показываем подтверждение
        await _show_confirm(message, state)


# ── Показать подтверждение ────────────────────────────────────────────────────

async def _show_confirm(message: Message, state: FSMContext) -> None:
    data          = await state.get_data()
    row_data      = data["row_data"]
    template_name = data["template_name"]
    entity        = data.get("entity", "")
    collected     = data.get("collected_extra", {})

    full_name = row_data[config.COL["Полное ФИО"] - 1]
    position  = row_data[config.COL["Должность"] - 1]

    # Строим читаемые метки из EXTRA_FIELDS: {field_key: prompt_text}
    # Промпт выглядит как "💰 Введите оклад:" — берём его как метку
    extra_fields_def = config.EXTRA_FIELDS.get(template_name, [])
    labels = {field_key: prompt.rstrip(":").strip() for field_key, prompt, _ in extra_fields_def}

    extra_lines = ""
    for key, value in collected.items():
        label = labels.get(key, key)  # если метка не найдена — показываем ключ
        extra_lines += f"\n   {label}: <b>{escape(value)}</b>"

    text = (
        f"📋 <b>Подтвердите создание документа:</b>\n\n"
        f"👤 <b>Сотрудник:</b> {escape(full_name)}\n"
        f"💼 <b>Должность:</b> {escape(position)}\n"
        f"📄 <b>Шаблон:</b> {escape(template_name)}\n"
        f"🏢 <b>Юрлицо:</b> {entity or '—'}"
        + extra_lines
    )
    await message.answer(text, reply_markup=kb.confirm_kb(), parse_mode="HTML")
    await state.set_state(GenerateDocument.confirm)


# ── Шаг 6 — подтверждение и генерация ────────────────────────────────────────

@router.message(GenerateDocument.confirm)
async def process_confirm(message: Message, state: FSMContext) -> None:
    data          = await state.get_data()
    menu = kb.main_menu(data.get('_user_id', 0))
    await state.clear()
    if message.text != "✅ Подтвердить":
        await message.answer("Отменено.", reply_markup=menu)
        return
    row_data      = data["row_data"]
    template_name = data["template_name"]
    entity        = data.get("entity", "")
    collected     = data.get("collected_extra", {})
    prikaz_num    = data.get("prikaz_num")   # None если не приказ

    # Строим extra_vars: {{{TEMPLATE_VAR}}: value}
    extra_fields = config.EXTRA_FIELDS.get(template_name, [])
    extra_vars = {}
    for field_key, _, template_var in extra_fields:
        if field_key in collected:
            extra_vars[template_var] = collected[field_key]

    await message.answer("⏳ Генерирую документ...", reply_markup=kb.remove_kb)

    try:
        result = await to_thread(
            google_api.generate_document,
            template_name, entity, row_data, extra_vars, prikaz_num
        )
        nums = result["numbers"]
        num_lines = ""
        if nums["prikaz"]:  num_lines += f"\n📋 Номер приказа: <b>{nums['prikaz']}</b>"
        if nums["dogovor"]: num_lines += f"\n📄 Номер договора: <b>{nums['dogovor']}</b>"
        if nums["spravka"]: num_lines += f"\n📑 Номер справки: <b>{nums['spravka']}</b>"
        if nums["dov"]:     num_lines += f"\n📑 Номер доверенности: <b>{nums['dov']}</b>"
        if nums["ish"]:     num_lines += f"\n📤 Исходящий номер: <b>{nums['ish']}</b>"

        await message.answer(
            f"✅ <b>Документ создан!</b>\n\n"
            f"📁 {escape(result['doc_name'])}"
            + num_lines +
            f"\n\n🔗 <a href=\"{result['pdf_url']}\">Открыть PDF</a>",
            reply_markup=menu,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except FileNotFoundError as e:
        await message.answer(
            f"❌ Шаблон не найден:\n<code>{escape(str(e))}</code>\n\n"
            "Убедитесь, что шаблон находится в папке «Шаблоны» на Google Drive.",
            reply_markup=menu,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка генерации документа")
        await message.answer(
            f"❌ Ошибка:\n<code>{escape(str(e))}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )


# ── Вспомогательные callbacks ─────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "gen:cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.delete()
    await call.message.answer("Отменено.", reply_markup=kb.main_menu(call.from_user.id))
    await call.answer()


@router.callback_query(lambda c: c.data == "gen:back")
async def cb_back(call: CallbackQuery, state: FSMContext) -> None:
    await call.message.edit_text(
        "Выберите тип документа:", reply_markup=kb.doc_category_kb()
    )
    await call.answer()
