"""HR Telegram Bot — точка входа."""
import asyncio
import logging
import os
import socket
import ssl
import sys

import aiohttp
import certifi
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from core.middlewares import AccessControlMiddleware
from handlers import (
    common, add_employee, fire_employee,
    upload_document, generate_document, evaluate_360,
    employee_files, employee_card, edit_employee, statistics, admin,
    hr_onboarding,
)
from core.scheduler import setup_scheduler
from models.db import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class IPv4Session(AiohttpSession):
    """AiohttpSession, принудительно использующий IPv4."""
    async def create_session(self) -> aiohttp.ClientSession:
        if isinstance(self._session, aiohttp.ClientSession) and not self._session.closed:
            return self._session
        ssl_ctx   = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx, family=socket.AF_INET)
        self._session = aiohttp.ClientSession(connector=connector)
        return self._session


def _validate_config() -> None:
    errors = []
    if not config.BOT_TOKEN:
        errors.append("BOT_TOKEN не задан")
    if not config.ALLOWED_USERS:
        errors.append("ALLOWED_USERS не задан")
    if not config.SPREADSHEET_ID:
        errors.append("SPREADSHEET_ID не задан")
    if not config.HR_DRIVE_FOLDER_ID:
        errors.append("HR_DRIVE_FOLDER_ID не задан")
    if not os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
        errors.append(f"Файл ключа {config.GOOGLE_CREDENTIALS_FILE!r} не найден")
    if errors:
        for err in errors:
            logger.error("Конфигурация: %s", err)
        sys.exit(1)


async def _check_db() -> None:
    """Проверить соединение с PostgreSQL при старте."""
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL: соединение установлено")
    except Exception as e:
        logger.error("PostgreSQL недоступен: %s", e)
        sys.exit(1)


async def main() -> None:
    _validate_config()
    await _check_db()
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=IPv4Session(timeout=30),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(AccessControlMiddleware())

    # admin первым — /myid должна работать без проверки доступа (middleware пропускает)
    dp.include_router(admin.router)
    # common вторым — чтобы /start и 🚫 Отмена перехватывались до FSM-роутеров
    dp.include_router(common.router)
    dp.include_router(add_employee.router)
    dp.include_router(fire_employee.router)
    dp.include_router(employee_card.router)
    dp.include_router(edit_employee.router)
    dp.include_router(upload_document.router)
    dp.include_router(generate_document.router)
    dp.include_router(evaluate_360.router)
    dp.include_router(employee_files.router)
    dp.include_router(statistics.router)
    dp.include_router(hr_onboarding.router)

    setup_scheduler(bot)

    logger.info("Бот запущен. Пользователи: %s", config.ALLOWED_USERS)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
