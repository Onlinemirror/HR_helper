from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

import config


class AccessControlMiddleware(BaseMiddleware):
    """Блокирует всех пользователей, чей Telegram ID не в ALLOWED_USERS."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id not in config.ALLOWED_USERS:
            if isinstance(event, Message):
                await event.answer(
                    "⛔ У вас нет доступа к этому боту.\n"
                    "Обратитесь к администратору HR-отдела."
                )
            return  # Не передаём событие дальше
        return await handler(event, data)
