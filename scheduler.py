"""
Планировщик ежедневных HR-проверок.
Каждый день в 09:00 бот отправляет уведомления всем ALLOWED_USERS.
"""
import logging
from asyncio import to_thread

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

import config
import google_api

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Almaty")


async def _send_all(bot: Bot, text: str) -> None:
    for uid in config.ALLOWED_USERS:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception as e:
            logger.warning("Не удалось отправить уведомление %s: %s", uid, e)


async def daily_check(bot: Bot) -> None:
    logger.info("Запуск ежедневных HR-проверок")

    # ── Дни рождения ──────────────────────────────────────────────────────
    try:
        bdays = await to_thread(google_api.check_birthdays)
        if bdays:
            text = (
                f"🎂 <b>Ближайшие дни рождения (±{config.DAYS_BEFORE_BDAY} дн.):</b>\n\n"
                + "\n".join(bdays)
            )
            await _send_all(bot, text)
    except Exception as e:
        logger.error("Ошибка проверки ДР: %s", e)

    # ── Истекающие договоры ────────────────────────────────────────────────
    try:
        expiry = await to_thread(google_api.check_contract_expiry)
        if expiry:
            text = (
                f"⚠️ <b>Договоры, истекающие в ближайшие {config.DAYS_BEFORE_EXPIRY} дней:</b>\n\n"
                + "\n".join(expiry)
            )
            await _send_all(bot, text)
    except Exception as e:
        logger.error("Ошибка проверки договоров: %s", e)

    # ── Конец испытательного срока ─────────────────────────────────────────
    try:
        probation = await to_thread(google_api.check_probation)
        if probation:
            text = (
                "⏳ <b>Конец испытательного срока (ближайшие 7 дней):</b>\n\n"
                + "\n".join(probation)
                + "\n\nНеобходимо принять решение и оформить приказ."
            )
            await _send_all(bot, text)
    except Exception as e:
        logger.error("Ошибка проверки испытательного срока: %s", e)


def setup_scheduler(bot: Bot) -> None:
    scheduler.add_job(
        daily_check,
        trigger="cron",
        hour=9,
        minute=0,
        args=[bot],
        id="daily_hr_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Планировщик запущен (ежедневно 09:00 Almaty)")
