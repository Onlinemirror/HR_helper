from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)


# ── Reply-клавиатуры ──────────────────────────────────────────────────────────

def main_menu(user_id: int = 0) -> ReplyKeyboardMarkup:
    """Главное меню. Для администраторов показывает блок управления пользователями."""
    from . import user_store
    is_admin = user_id and user_store.is_admin(user_id)
    admin_rows = [
        [KeyboardButton(text="👥 HR-менеджеры")],
        [KeyboardButton(text="➕ Добавить HR-менеджера"),
         KeyboardButton(text="➖ Удалить HR-менеджера")],
    ] if is_admin else []
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить сотрудника"),
             KeyboardButton(text="❌ Уволить сотрудника")],
            [KeyboardButton(text="👤 Карточка сотрудника"),
             KeyboardButton(text="✏️ Редактировать сотрудника")],
            [KeyboardButton(text="📋 Создать документ"),
             KeyboardButton(text="📄 Загрузить файл")],
            [KeyboardButton(text="📥 Файлы сотрудника"),
             KeyboardButton(text="📁 Синхронизировать папки Drive")],
            [KeyboardButton(text="📊 Оценка 360"),
             KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📜 История изменений"),
             KeyboardButton(text="🔔 Запустить проверку уведомлений")],
            [KeyboardButton(text="🎓 Добавить новичка"),
             KeyboardButton(text="📋 Список новичков")],
        ] + admin_rows,
        resize_keyboard=True,
    )


def main_menu_admin() -> ReplyKeyboardMarkup:
    """Алиас для обратной совместимости."""
    return main_menu()


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


def accept_num_kb() -> ReplyKeyboardMarkup:
    """Клавиатура для шага ввода номера приказа."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Принять")],
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
    ("📋 Приказы ТОО",     "cat:prikaz:TOO"),
    ("📄 Договоры ТОО",    "cat:dogovor:TOO"),
    ("📝 Прочие документы", "cat:prochie:"),
]

# Индексированный список всех шаблонов: (label, base_name)
# entity_suffix подставляется при построении keyboard
# Только шаблоны с реальными файлами на Google Drive
PRIKAZ_TYPES = [
    ("Приём",      "Шаблон_Приказ_прием"),
    ("Увольнение", "Шаблон_Приказ_увольнение"),
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

PROCHIE_TYPES = [
    ("Оффер",                          "Шаблон_Оффер"),
    ("Согласие на обработку ПД",       "Шаблон_Согласие_на_обработку"),
    ("Соглашение о неконкуренции",     "Шаблон_Соглашение_о_неконкуренции"),
    ("NDA (ТОО)",                      "Шаблон_NDA_ТОО"),
    ("NDA (ЧК)",                       "Шаблон_NDA_ЧК"),
    ("Доп. соглашение к ТД (ТОО)",    "Шаблон_Доп_соглашение_к_ТД_ТОО"),
    ("Доп. соглашение к ГПХ (ЧК)",   "Шаблон_Доп_соглашение_к_ГПХ_ЧК"),
    ("Перечень КТ (Прил. к NDA)",     "Шаблон_Перечень_КТ"),
    ("Положение о КТ",                "Шаблон_Положение_о_КТ"),
]

# Глобальный плоский список для разрешения индекса → шаблон
_ALL_TEMPLATES: list[str] = []

def _build_template_index() -> None:
    global _ALL_TEMPLATES
    seen = []
    # Приказы и договоры — только ТОО (ЧК-шаблонов на Drive нет кроме увольнения,
    # но категория ЧК убрана из меню до появления всех файлов)
    for _, base in PRIKAZ_TYPES:
        seen.append(f"{base}_ТОО")
    for _, base in DOGOVOR_TYPES:
        seen.append(f"{base}_ТОО")
    for _, base in PROCHIE_TYPES:
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
    elif category == "prochie":
        types = PROCHIE_TYPES
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


def subfolders_kb(subfolders: list[dict]) -> InlineKeyboardMarkup:
    """
    Inline-клавиатура для выбора папки сотрудника.
    subfolders — список {"id": ..., "name": ...}
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f["name"], callback_data=f"dlfolder:{i}")]
            for i, f in enumerate(subfolders)
        ] + [[InlineKeyboardButton(text="🚫 Отмена", callback_data="dl:cancel")]]
    )


def upload_category_kb(categories: list[str]) -> InlineKeyboardMarkup:
    """Inline-клавиатура выбора категории загружаемого документа."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=cat,
                callback_data=f"ucat:{i}",
            )]
            for i, cat in enumerate(categories)
        ] + [[InlineKeyboardButton(text="🚫 Отмена", callback_data="upload:cancel")]]
    )


def employee_select_kb(employees: list[tuple[int, list[str]]], prefix: str) -> InlineKeyboardMarkup:
    """
    Inline-клавиатура выбора сотрудника из списка найденных по ФИО.
    prefix — уникальный префикс хендлера (gen_emp, fire_emp, dl_emp, up_emp, card_emp, edit_emp).
    """
    import config as _cfg
    buttons = []
    for i, (row_idx, row_data) in enumerate(employees):
        fio  = row_data[_cfg.COL["Полное ФИО"] - 1]
        dept = row_data[_cfg.COL["Отдел"] - 1]
        label = f"{fio} ({dept})" if dept else fio
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"{prefix}:{i}")])
    buttons.append([InlineKeyboardButton(text="🚫 Отмена", callback_data=f"{prefix}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def skip_inline_kb() -> InlineKeyboardMarkup:
    """Inline-кнопка «Пропустить» — видна даже когда открыта клавиатура."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Пропустить →", callback_data="field:skip"),
    ]])


def contract_type_inline_kb() -> InlineKeyboardMarkup:
    """Выбор типа договора + Пропустить — всё inline."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ТД", callback_data="contract:ТД"),
         InlineKeyboardButton(text="ГПХ", callback_data="contract:ГПХ")],
        [InlineKeyboardButton(text="Пропустить →", callback_data="field:skip")],
    ])


def legal_entity_inline_kb() -> InlineKeyboardMarkup:
    """Выбор юрлица ЧК / ТОО."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ЧК", callback_data="entity:ЧК"),
         InlineKeyboardButton(text="ТОО", callback_data="entity:ТОО")],
        [InlineKeyboardButton(text="Пропустить →", callback_data="field:skip")],
    ])


def edit_fields_kb() -> InlineKeyboardMarkup:
    """Список редактируемых полей."""
    fields = [
        ("👤 ФИО (Фамилия)",   "Фамилия"),
        ("👤 Имя",              "Имя"),
        ("👤 Отчество",         "Отчество"),
        ("📅 Дата рождения",    "Дата рождения"),
        ("🔢 ИИН",              "ИИН"),
        ("🏙 Город",            "Город"),
        ("🏢 Отдел",            "Отдел"),
        ("💼 Должность",        "Должность"),
        ("📋 Тип договора",     "Тип договора"),
        ("📅 Дата приёма",      "Дата приёма"),
        ("📞 Телефон",          "Телефон"),
        ("📧 Email",            "Email"),
        ("🏠 Адрес",            "Адрес"),
        ("👔 Руководитель",     "Руководитель"),
        ("📌 Статус",           "Статус"),
        ("📝 Примечание",       "Примечание"),
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"editf:{key}")]
            for label, key in fields
        ] + [[InlineKeyboardButton(text="🚫 Отмена", callback_data="edit:cancel")]]
    )


def score_kb(criterion_key: str) -> InlineKeyboardMarkup:
    """Inline-клавиатура для оценки 1–5."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=str(i), callback_data=f"score:{criterion_key}:{i}")
            for i in range(1, 6)
        ]]
    )
