"""FSM оценки 360: выбор сотрудника → 5 критериев (inline 1–5) → комментарии → запись."""
import logging
from asyncio import to_thread
from html import escape

from aiogram import F, Router

CANCEL = F.text != "🚫 Отмена"
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from integrations import google_api
from core import keyboards as kb
from core.states import Evaluate360

logger = logging.getLogger(__name__)
router = Router()

CRITERIA = [
    ("quality",        "⭐ Качество работы"),
    ("teamwork",       "🤝 Командная работа"),
    ("initiative",     "💡 Инициативность"),
    ("communication",  "💬 Коммуникация"),
    ("knowledge",      "🎓 Профессиональные знания"),
]


# ── Шаг 1 — запуск ────────────────────────────────────────────────────────────

@router.message(lambda m: m.text == "📊 Оценка 360")
async def start_360(message: Message, state: FSMContext) -> None:
    await state.set_state(Evaluate360.waiting_employee)
    await message.answer(
        "🔍 Введите <b>ИИН</b> или <b>ID</b> оцениваемого сотрудника:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


# ── Шаг 2 — поиск сотрудника ──────────────────────────────────────────────────

@router.message(Evaluate360.waiting_employee, CANCEL)
async def process_employee_360(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    result = await to_thread(google_api.find_employee, query)

    if result is None:
        # Пробуем поиск по ФИО
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
            await state.update_data(emp_candidates=candidates)
            await message.answer(
                "🔍 Найдено несколько сотрудников. Выберите нужного:",
                reply_markup=kb.employee_select_kb(candidates, "eval_emp"),
            )
            return

    _, row_data = result
    await _start_scoring(message, state, row_data)


# ── Выбор из списка найденных по ФИО ─────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("eval_emp:"))
async def cb_eval_select(call: CallbackQuery, state: FSMContext) -> None:
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
    _, row_data = candidates[idx]
    await call.message.delete()
    await _start_scoring(call.message, state, row_data)
    await call.answer()


async def _start_scoring(message: Message, state: FSMContext, row_data: list) -> None:
    """Начинаем опрос оценок после того как сотрудник найден."""
    import config as cfg
    full_name = row_data[cfg.COL["Полное ФИО"] - 1]
    await state.update_data(row_data=row_data, scores={}, criteria_idx=0)
    await message.answer(
        f"✅ Оцениваете: <b>{escape(full_name)}</b>\n\nОцените каждый критерий от 1 до 5.",
        reply_markup=kb.remove_kb,
        parse_mode="HTML",
    )
    key, label = CRITERIA[0]
    await message.answer(label, reply_markup=kb.score_kb(key))
    await state.set_state(Evaluate360.score_quality)


# ── Шаги 3-7 — оценки по критериям (единый обработчик callback) ──────────────

SCORE_STATES = [
    Evaluate360.score_quality,
    Evaluate360.score_teamwork,
    Evaluate360.score_initiative,
    Evaluate360.score_communication,
    Evaluate360.score_knowledge,
]


@router.callback_query(lambda c: c.data and c.data.startswith("score:"))
async def process_score(call: CallbackQuery, state: FSMContext) -> None:
    parts     = call.data.split(":")  # score:quality:4
    criterion = parts[1]
    score     = int(parts[2])

    data    = await state.get_data()
    scores  = data.get("scores", {})
    idx     = data.get("criteria_idx", 0)

    scores[criterion] = score
    idx += 1
    await state.update_data(scores=scores, criteria_idx=idx)
    await call.message.edit_text(
        f"{call.message.text}  →  <b>{score}</b>", parse_mode="HTML"
    )

    if idx < len(CRITERIA):
        key, label = CRITERIA[idx]
        await call.message.answer(label, reply_markup=kb.score_kb(key))
        await state.set_state(SCORE_STATES[idx])
    else:
        # Все оценки собраны — просим текст
        await call.message.answer(
            "💪 Опишите <b>сильные стороны</b> сотрудника:",
            reply_markup=kb.cancel_kb(),
            parse_mode="HTML",
        )
        await state.set_state(Evaluate360.waiting_strengths)

    await call.answer()


# ── Шаг 8 — сильные стороны ───────────────────────────────────────────────────

@router.message(Evaluate360.waiting_strengths, CANCEL)
async def process_strengths(message: Message, state: FSMContext) -> None:
    await state.update_data(strengths=message.text.strip())
    await message.answer(
        "🔧 Что можно <b>улучшить</b>?",
        parse_mode="HTML",
    )
    await state.set_state(Evaluate360.waiting_improve)


# ── Шаг 9 — что улучшить → подтверждение ─────────────────────────────────────

@router.message(Evaluate360.waiting_improve, CANCEL)
async def process_improve(message: Message, state: FSMContext) -> None:
    await state.update_data(improve=message.text.strip())
    data      = await state.get_data()
    row_data  = data["row_data"]
    scores    = data["scores"]
    full_name = row_data[4]
    avg       = round(sum(scores.values()) / len(scores), 2) if scores else 0

    scores_text = "\n".join(
        f"  {label}: <b>{scores.get(key, '—')}</b>"
        for key, label in CRITERIA
    )
    await message.answer(
        f"📊 <b>Итоги оценки:</b>\n\n"
        f"👤 Сотрудник: <b>{escape(full_name)}</b>\n"
        f"⭐ Средний балл: <b>{avg}</b>\n\n"
        f"{scores_text}\n\n"
        f"💪 Сильные стороны: {escape(data.get('strengths', ''))}\n"
        f"🔧 Улучшить: {escape(message.text.strip())}\n\n"
        "Сохранить оценку?",
        reply_markup=kb.confirm_kb(),
        parse_mode="HTML",
    )
    await state.set_state(Evaluate360.confirm)


# ── Шаг 10 — сохранение ───────────────────────────────────────────────────────

@router.message(Evaluate360.confirm)
async def process_360_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    menu = kb.main_menu(message.from_user.id)
    await state.clear()
    if message.text != "✅ Подтвердить":
        await message.answer("Отменено.", reply_markup=menu)
        return

    evaluator = (f"@{message.from_user.username}"
                 if message.from_user.username
                 else str(message.from_user.id))
    try:
        await to_thread(
            google_api.save_360_evaluation,
            evaluator,
            data["row_data"],
            data["scores"],
            data.get("strengths", ""),
            data.get("improve", ""),
        )
        await message.answer("✅ Оценка сохранена в таблицу.", reply_markup=menu)
    except Exception as e:
        logger.exception("Ошибка сохранения оценки 360")
        await message.answer(
            f"❌ Ошибка:\n<code>{escape(str(e))}</code>",
            reply_markup=menu,
            parse_mode="HTML",
        )
