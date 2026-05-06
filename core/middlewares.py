from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from . import user_store


class AccessControlMiddleware(BaseMiddleware):
    """Проверяет доступ и кладёт роль пользователя в data["role"].

    Роли: 'admin', 'hr', 'unknown'.
    Пропускает всех для /myid — чтобы незнакомый мог узнать свой ID и сообщить администратору.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return

        # /myid доступна всем — для получения своего Telegram ID
        if isinstance(event, Message) and event.text and event.text.strip() == "/myid":
            return await handler(event, data)

        role = user_store.get_role(user.id)
        data["role"] = role

        if role == "unknown":
            if isinstance(event, Message):
                await event.answer(
                    f"⛔ У вас нет доступа к этому боту.\n"
                    f"Сообщите администратору ваш Telegram ID: <code>{user.id}</code>",
                    parse_mode="HTML",
                )
            return

        return await handler(event, data)
