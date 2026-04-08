from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)


# ── Reply-клавиатуры ──────────────────────────────────────────────────────────

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить сотрудника"),
             KeyboardButton(text="❌ Уволить сотрудника")],
            [KeyboardButton(text="📋 Создать документ"),
             KeyboardButton(text="📄 Загрузить файл")],
            [KeyboardButton(text="📊 Оценка 360")],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚫 Отмена")]],
        resize_keyboard=True,
    )


def skip_or_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить")],
            [KeyboardButton(text="🚫 Отмена")],
        ],
        resize_keyboard=True,
    )


def confirm_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подтвердить"),
             KeyboardButton(text="🚫 Отмена")],
        ],
        resize_keyboard=True,
    )


remove_kb = ReplyKeyboardRemove()


# ── Inline-клавиатуры для генерации документов ────────────────────────────────

DOC_CATEGORIES = [
    ("📋 Приказы ТОО",  "cat:prikaz:TOO"),
    ("📋 Приказы ЧК",   "cat:prikaz:CHK"),
    ("📄 Договоры ТОО", "cat:dogovor:TOO"),
    ("📄 Договоры ЧК",  "cat:dogovor:CHK"),
    ("📑 Справки",       "cat:spravka:"),
]

# Индексированный список всех шаблонов: (label, base_name)
# entity_suffix подставляется при построении keyboard
PRIKAZ_TYPES = [
    ("Приём",            "Шаблон_Приказ_прием"),
    ("Увольнение",       "Шаблон_Приказ_увольнение"),
    ("Перевод",          "Шаблон_Приказ_перевод"),
    ("Отпуск",           "Шаблон_Приказ_отпуск"),
    ("Изменение оклада", "Шаблон_Приказ_изменение_оклада"),
]

DOGOVOR_TYPES = [
    ("Трудовой договор (ТД)", "Шаблон_Договор_ТД"),
    ("Договор ГПХ",           "Шаблон_Договор_ГПХ"),
]

SPRAVKA_TYPES = [
    ("Справка с места работы", "Шаблон_Справка_с_места_работы"),
    ("Доверенность",           "Шаблон_Доверенность"),
    ("Уведомление",            "Шаблон_Уведомление"),
]

# Глобальный плоский список для разрешения индекса → шаблон
_ALL_TEMPLATES: list[str] = []

def _build_template_index() -> None:
    global _ALL_TEMPLATES
    seen = []
    for entity in ("ТОО", "ЧК"):
        for _, base in PRIKAZ_TYPES:
            seen.append(f"{base}_{entity}")
        for _, base in DOGOVOR_TYPES:
            seen.append(f"{base}_{entity}")
    for _, base in SPRAVKA_TYPES:
        seen.append(base)
    _ALL_TEMPLATES = seen

_build_template_index()


def template_by_index(idx: int) -> str | None:
    if 0 <= idx < len(_ALL_TEMPLATES):
        return _ALL_TEMPLATES[idx]
    return None


def doc_category_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=cb)]
            for label, cb in DOC_CATEGORIES
        ] + [[InlineKeyboardButton(text="🚫 Отмена", callback_data="gen:cancel")]]
    )


def doc_type_kb(category: str, entity_code: str) -> InlineKeyboardMarkup:
    """entity_code: 'TOO' | 'CHK' | ''"""
    entity = {"TOO": "ТОО", "CHK": "ЧК"}.get(entity_code, "")

    if category == "prikaz":
        types = PRIKAZ_TYPES
    elif category == "dogovor":
        types = DOGOVOR_TYPES
    else:
        types = SPRAVKA_TYPES

    buttons = []
    for label, base in types:
        full_name = f"{base}_{entity}" if entity else base
        idx = _ALL_TEMPLATES.index(full_name) if full_name in _ALL_TEMPLATES else -1
        if idx >= 0:
            buttons.append([InlineKeyboardButton(
                text=label, callback_data=f"dt:{idx}"  # короткий callback
            )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="gen:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def score_kb(criterion_key: str) -> InlineKeyboardMarkup:
    """Inline-клавиатура для оценки 1–5."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=str(i), callback_data=f"score:{criterion_key}:{i}")
            for i in range(1, 6)
        ]]
    )
