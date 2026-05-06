"""
Хранилище пользователей бота.

Роли:
- Администраторы (ADMIN_USERS) — из .env, неизменяемы без деплоя. Полный доступ.
- HR-менеджеры (HR_USERS) — из hr_users.json, управляются администратором через бота.
- ALLOWED_USERS — объединение ADMIN_USERS | HR_USERS, используется планировщиком.
"""
import json
import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_HR_STORE_FILE = Path("credentials/hr_users.json")

# Администраторы из .env — неизменяемы, управляют HR-менеджерами
ADMIN_USERS: set[int] = set(config.ALLOWED_USERS)

# HR-менеджеры — добавляются/удаляются через бота
HR_USERS: set[int] = set()

# Все кто получает HR-уведомления от планировщика
ALLOWED_USERS: set[int] = set(config.ALLOWED_USERS)


def _load() -> None:
    global HR_USERS, ALLOWED_USERS
    if _HR_STORE_FILE.exists():
        try:
            data = json.loads(_HR_STORE_FILE.read_text(encoding="utf-8"))
            HR_USERS = set(data.get("users", []))
            ALLOWED_USERS = ADMIN_USERS | HR_USERS
            logger.info("Загружено HR-менеджеров: %d", len(HR_USERS))
        except Exception as e:
            logger.error("Ошибка чтения %s: %s", _HR_STORE_FILE, e)


def _save() -> None:
    try:
        _HR_STORE_FILE.write_text(
            json.dumps({"users": sorted(HR_USERS)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("Ошибка сохранения %s: %s", _HR_STORE_FILE, e)


def add_hr_user(user_id: int) -> bool:
    """Добавить HR-менеджера. False если уже существует или является администратором."""
    if user_id in ADMIN_USERS or user_id in HR_USERS:
        return False
    HR_USERS.add(user_id)
    ALLOWED_USERS.add(user_id)
    _save()
    return True


def remove_hr_user(user_id: int) -> bool:
    """Удалить HR-менеджера. False если не найден или является администратором."""
    if user_id in ADMIN_USERS:
        return False
    if user_id not in HR_USERS:
        return False
    HR_USERS.discard(user_id)
    ALLOWED_USERS.discard(user_id)
    _save()
    return True


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USERS


def is_hr(user_id: int) -> bool:
    """True для HR-менеджеров из файла (не считая администраторов)."""
    return user_id in HR_USERS


def get_role(user_id: int) -> str:
    """Вернуть роль: 'admin', 'hr' или 'unknown'."""
    if user_id in ADMIN_USERS:
        return "admin"
    if user_id in HR_USERS:
        return "hr"
    return "unknown"


def list_hr_users() -> list[int]:
    """Список HR-менеджеров добавленных через бота (не из .env)."""
    return sorted(HR_USERS)


# Загружаем при импорте
_load()
