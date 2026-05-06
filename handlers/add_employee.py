"""FSM-диалог добавления нового сотрудника."""
import logging
import re
from asyncio import to_thread
from html import escape

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from integrations import google_api
from core import keyboards as kb
from core.states import AddEmployee

logger = logging.getLogger(__name__)
router = Router()

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

CANCEL = lambda m: m.text != "🚫 Отмена"  # noqa: E731


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "➕ Добавить сотрудника")
async def start_add(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.last_name)
    await state.update_data(_user_id=message.from_user.id)
    await message.answer(
        "📝 Введите <b>фамилию</b> сотрудника:\n\n"
        "<i>Или введите все данные через запятую для быстрого добавления:\n"
        "Фамилия, Имя, Отчество, Дата рождения, ИИН, Должность, Город, Отдел, "
        "Тип договора, Юрлицо, Телефон, Email, Руководитель\n"
        "Пустые поля — прочерк: <code>-</code></i>",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Быстрое добавление через запятую ─────────────────────────────────────────

# Порядок полей для быстрого ввода
_QUICK_FIELDS = [
    "last_name", "first_name", "middle_name", "birth_date", "iin",
    "position", "city", "department", "contract_type", "legal_entity",
    "phone", "email", "manager",
]

def _parse_quick(text: str) -> dict | None:
    """
    Парсит строку вида «Фамилия, Имя, -, ...» в словарь данных сотрудника.
    Возвращает None если полей меньше 2 (не похоже на быстрый ввод).
    Прочерк (-) превращается в пустую строку.
    """
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 2:
        return None
    result = {}
    for i, field in enumerate(_QUICK_FIELDS):
        value = parts[i] if i < len(parts) else ""
        result[field] = "" if value in ("-", "—") else value
    return result


# ── Шаг 2 — Фамилия → Имя (или быстрый ввод) ─────────────────────────────────

@router.message(AddEmployee.last_name, lambda m: CANCEL(m))
async def process_last_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Фамилия не может быть пустой. Попробуйте ещё раз:")
        return

    # Если есть запятые — пробуем быстрый ввод
    if "," in text:
        parsed = _parse_quick(text)
        if parsed:
            # Проверяем обязательные поля
            errors = []
            if not parsed.get("last_name"):
                errors.append("Фамилия")
            if not parsed.get("first_name"):
                errors.append("Имя")
            if parsed.get("iin") and (not parsed["iin"].isdigit() or len(parsed["iin"]) != 12):
                errors.append("ИИН (должен быть 12 цифр)")
            if errors:
                await message.answer(
                    f"⚠️ Ошибка в полях: <b>{', '.join(errors)}</b>. Проверьте и попробуйте ещё раз:",
                    parse_mode="HTML",
                )
                return
            # Проверяем уникальность ИИН если он указан
            if parsed.get("iin"):
                existing = await to_thread(google_api.find_employee, parsed["iin"])
                if existing:
                    _, row = existing
                    await message.answer(
                        f"⚠️ Сотрудник с ИИН <b>{parsed['iin']}</b> уже существует: <b>{row[4]}</b>.",
                        parse_mode="HTML",
                    )
                    return
            await state.update_data(**parsed)
            await _show_confirm(message, state)
            return

    # Обычный пошаговый ввод
    await state.update_data(last_name=text)
    await state.set_state(AddEmployee.first_name)
    await message.answer("📝 Введите <b>имя</b> сотрудника:", parse_mode="HTML")


# ── Шаг 3 — Имя → Отчество ────────────────────────────────────────────────────

@router.message(AddEmployee.first_name, lambda m: CANCEL(m))
async def process_first_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Имя не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(first_name=text)
    await state.set_state(AddEmployee.middle_name)
    await message.answer(
        "📝 Введите <b>отчество</b>:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )
    await message.answer("или пропустите 👇", reply_markup=kb.skip_inline_kb())


# ── Шаг 4 — Отчество → Дата рождения ─────────────────────────────────────────

@router.message(AddEmployee.middle_name, lambda m: CANCEL(m))
async def process_middle_name(message: Message, state: FSMContext) -> None:
    await state.update_data(middle_name=message.text.strip())
    await _ask_birth_date(message, state)


async def _ask_birth_date(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.birth_date)
    await message.answer(
        "📅 Введите <b>дату рождения</b> (ДД.ММ.ГГГГ):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )
    await message.answer("или пропустите 👇", reply_markup=kb.skip_inline_kb())


# ── Шаг 5 — Дата рождения → ИИН ──────────────────────────────────────────────

@router.message(AddEmployee.birth_date, lambda m: CANCEL(m))
async def process_birth_date(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not _DATE_RE.match(text):
        await message.answer("⚠️ Формат: ДД.ММ.ГГГГ. Попробуйте ещё раз:")
        return
    await state.update_data(birth_date=text)
    await _ask_iin(message, state)


async def _ask_iin(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.iin)
    await message.answer(
        "🔢 Введите <b>ИИН</b> сотрудника (12 цифр):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 6 — ИИН → Должность ───────────────────────────────────────────────────

@router.message(AddEmployee.iin, lambda m: CANCEL(m))
async def process_iin(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit() or len(text) != 12:
        await message.answer("⚠️ ИИН должен состоять ровно из 12 цифр. Попробуйте ещё раз:")
        return
    existing = await to_thread(google_api.find_employee, text)
    if existing:
        _, row = existing
        await message.answer(
            f"⚠️ Сотрудник с ИИН <b>{text}</b> уже существует: <b>{row[4]}</b>.\n"
            "Введите другой ИИН или нажмите «🚫 Отмена».",
            parse_mode="HTML",
        )
        return
    await state.update_data(iin=text)
    await state.set_state(AddEmployee.position)
    await message.answer("💼 Введите <b>должность</b> сотрудника:", parse_mode="HTML")


# ── Шаг 7 — Должность → Город ─────────────────────────────────────────────────

@router.message(AddEmployee.position, lambda m: CANCEL(m))
async def process_position(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Должность не может быть пустой. Попробуйте ещё раз:")
        return
    await state.update_data(position=text)
    await state.set_state(AddEmployee.city)
    await message.answer("🏙 Введите <b>город</b> сотрудника:", parse_mode="HTML")


# ── Шаг 8 — Город → Отдел ─────────────────────────────────────────────────────

@router.message(AddEmployee.city, lambda m: CANCEL(m))
async def process_city(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Город не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(city=text)
    await state.set_state(AddEmployee.department)
    await message.answer("🏢 Введите <b>отдел</b> сотрудника:", parse_mode="HTML")


# ── Шаг 9 — Отдел → Тип договора ─────────────────────────────────────────────

@router.message(AddEmployee.department, lambda m: CANCEL(m))
async def process_department(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text:
        await message.answer("Отдел не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(department=text)
    await _ask_contract_type(message, state)


async def _ask_contract_type(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.contract_type)
    await message.answer(
        "📋 Выберите <b>тип договора</b>:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )
    await message.answer("👇", reply_markup=kb.contract_type_inline_kb())


# ── Callback: выбор типа договора ─────────────────────────────────────────────

@router.callback_query(
    lambda c: c.data and c.data.startswith("contract:"),
    lambda c: True,  # работает в любом состоянии этого роутера
)
async def cb_contract_type(call: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    if current != AddEmployee.contract_type:
        await call.answer()
        return
    contract = call.data.split(":")[1]
    await state.update_data(contract_type=contract)
    await call.message.edit_text(f"📋 Тип договора: <b>{contract}</b>", parse_mode="HTML")
    await call.answer()
    await _ask_legal_entity(call.message, state)


# ── Шаг 10 — Тип договора (текст) → ЧК/ТОО ──────────────────────────────────

@router.message(AddEmployee.contract_type, lambda m: CANCEL(m))
async def process_contract_type(message: Message, state: FSMContext) -> None:
    await state.update_data(contract_type=message.text.strip())
    await _ask_legal_entity(message, state)


# ── Шаг 10б — Выбор юрлица (ЧК / ТОО) ───────────────────────────────────────

async def _ask_legal_entity(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.legal_entity)
    await message.answer(
        "🏢 Выберите <b>юрлицо</b> (ЧК или ТОО):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )
    await message.answer("👇", reply_markup=kb.legal_entity_inline_kb())


@router.callback_query(lambda c: c.data and c.data.startswith("entity:"))
async def cb_legal_entity(call: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    if current != AddEmployee.legal_entity:
        await call.answer()
        return
    entity = call.data.split(":")[1]
    await state.update_data(legal_entity=entity)
    await call.message.edit_text(f"🏢 Юрлицо: <b>{entity}</b>", parse_mode="HTML")
    await call.answer()
    await _ask_phone(call.message, state)


@router.message(AddEmployee.legal_entity, lambda m: CANCEL(m))
async def process_legal_entity(message: Message, state: FSMContext) -> None:
    await state.update_data(legal_entity=message.text.strip())
    await _ask_phone(message, state)


async def _ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.phone)
    await message.answer(
        "📞 Введите <b>телефон</b>:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )
    await message.answer("или пропустите 👇", reply_markup=kb.skip_inline_kb())


# ── Шаг 11 — Телефон → Email ──────────────────────────────────────────────────

@router.message(AddEmployee.phone, lambda m: CANCEL(m))
async def process_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.text.strip())
    await _ask_email(message, state)


async def _ask_email(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.email)
    await message.answer(
        "📧 Введите <b>email</b>:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )
    await message.answer("или пропустите 👇", reply_markup=kb.skip_inline_kb())


# ── Шаг 12 — Email → Руководитель ────────────────────────────────────────────

@router.message(AddEmployee.email, lambda m: CANCEL(m))
async def process_email(message: Message, state: FSMContext) -> None:
    await state.update_data(email=message.text.strip())
    await _ask_manager(message, state)


async def _ask_manager(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.manager)
    await message.answer(
        "👔 Введите <b>руководителя</b> (ФИО):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )
    await message.answer("или пропустите 👇", reply_markup=kb.skip_inline_kb())


# ── Шаг 13 — Руководитель → Подтверждение ────────────────────────────────────

@router.message(AddEmployee.manager, lambda m: CANCEL(m))
async def process_manager(message: Message, state: FSMContext) -> None:
    await state.update_data(manager=message.text.strip())
    await _show_confirm(message, state)


async def _show_confirm(message: Message, state: FSMContext) -> None:
    await state.set_state(AddEmployee.confirm)
    data = await state.get_data()
    fio = " ".join(filter(None, [data["last_name"], data["first_name"], data.get("middle_name", "")]))
    summary = (
        "📋 <b>Проверьте данные сотрудника:</b>\n\n"
        f"👤 <b>ФИО:</b> {escape(fio)}\n"
        f"📅 <b>Дата рождения:</b> {escape(data.get('birth_date') or '—')}\n"
        f"🔢 <b>ИИН:</b> {escape(data.get('iin') or '—')}\n"
        f"💼 <b>Должность:</b> {escape(data.get('position') or '—')}\n"
        f"🏙 <b>Город:</b> {escape(data.get('city') or '—')}\n"
        f"🏢 <b>Отдел:</b> {escape(data.get('department') or '—')}\n"
        f"📋 <b>Тип договора:</b> {escape(data.get('contract_type') or '—')}\n"
        f"🏛 <b>Юрлицо:</b> {escape(data.get('legal_entity') or '—')}\n"
        f"📞 <b>Телефон:</b> {escape(data.get('phone') or '—')}\n"
        f"📧 <b>Email:</b> {escape(data.get('email') or '—')}\n"
        f"👔 <b>Руководитель:</b> {escape(data.get('manager') or '—')}\n\n"
        "Всё верно?"
    )
    await message.answer(summary, reply_markup=kb.confirm_kb(), parse_mode="HTML")


# ── Callback: Пропустить (inline) ─────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "field:skip")
async def cb_skip(call: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    await call.message.edit_reply_markup(reply_markup=None)  # убираем кнопку
    await call.answer("Пропущено")

    if current == AddEmployee.middle_name:
        await state.update_data(middle_name="")
        await _ask_birth_date(call.message, state)
    elif current == AddEmployee.birth_date:
        await state.update_data(birth_date="")
        await _ask_iin(call.message, state)
    elif current == AddEmployee.phone:
        await state.update_data(phone="")
        await _ask_email(call.message, state)
    elif current == AddEmployee.email:
        await state.update_data(email="")
        await _ask_manager(call.message, state)
    elif current == AddEmployee.manager:
        await state.update_data(manager="")
        await _show_confirm(call.message, state)
    elif current == AddEmployee.contract_type:
        await state.update_data(contract_type="")
        await _ask_legal_entity(call.message, state)
    elif current == AddEmployee.legal_entity:
        await state.update_data(legal_entity="")
        await _ask_phone(call.message, state)


# ── Шаг 14 — Подтверждение и запись ───────────────────────────────────────────

@router.message(AddEmployee.confirm)
async def process_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu = kb.main_menu(data.get('_user_id', 0))
    await state.clear()
    if message.text != "✅ Подтвердить":
        await message.answer("Действие отменено.", reply_markup=menu)
        return

    await message.answer("⏳ Создаю папку на Google Drive и записываю данные...",
                         reply_markup=kb.remove_kb)
    try:
        fio = " ".join(filter(None, [data["last_name"], data["first_name"], data.get("middle_name", "")]))
        employee_id = await to_thread(google_api.generate_employee_id, data["city"])
        folder_name = f"{employee_id} {fio}"

        _, folder_link = await to_thread(
            google_api.create_drive_folder, folder_name, google_api.config.HR_DRIVE_FOLDER_ID
        )
        await to_thread(google_api.add_employee, data, employee_id, folder_link)

        await message.answer(
            f"✅ Сотрудник успешно добавлен!\n\n"
            f"🆔 <b>ID:</b> {employee_id}\n"
            f"👤 <b>ФИО:</b> {escape(fio)}\n"
            f"📁 <b>Папка Drive:</b> <a href=\"{folder_link}\">открыть</a>",
            reply_markup=menu,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("Ошибка при добавлении сотрудника")
        await message.answer(
            f"❌ Ошибка при сохранении данных:\n<code>{escape(str(e))}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )
