"""Управление HR-менеджерами (только для администраторов из .env)."""
import logging
from html import escape

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from core import keyboards as kb
from core import user_store

logger = logging.getLogger(__name__)
router = Router()


class AdminAddHR(StatesGroup):
    waiting_id = State()


class AdminRemoveHR(StatesGroup):
    waiting_id = State()


def _admin_only(message: Message) -> bool:
    return user_store.is_admin(message.from_user.id)


async def _user_label(bot: Bot, user_id: int) -> str:
    """Подтянуть имя и username по Telegram ID.
    Работает только если пользователь уже писал боту.
    При ошибке возвращает пустую строку.
    """
    try:
        chat = await bot.get_chat(user_id)
        parts = [p for p in [chat.first_name, chat.last_name] if p]
        name = " ".join(parts)
        username = f" (@{chat.username})" if chat.username else ""
        return f"{name}{username}".strip()
    except Exception:
        return ""


# ── /myid — доступна всем ─────────────────────────────────────────────────────

@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    uid = message.from_user.id
    name = message.from_user.full_name
    await message.answer(
        f"👤 <b>{escape(name)}</b>\n"
        f"🆔 Ваш Telegram ID: <code>{uid}</code>\n\n"
        "Сообщите этот ID администратору для получения доступа.",
        parse_mode="HTML",
    )


# ── Список HR-менеджеров ──────────────────────────────────────────────────────

@router.message(lambda m: m.text == "👥 HR-менеджеры")
async def list_hr_managers(message: Message) -> None:
    if not _admin_only(message):
        await message.answer("⛔ Только для администраторов.")
        return

    admins = sorted(user_store.ADMIN_USERS)
    hr_list = user_store.list_hr_users()

    lines = ["👥 <b>Пользователи бота:</b>\n"]

    lines.append(f"⭐ <b>Администраторы ({len(admins)}):</b>")
    for uid in admins:
        label = await _user_label(message.bot, uid)
        suffix = f" — {escape(label)}" if label else ""
        lines.append(f"  • <code>{uid}</code>{suffix}")

    if hr_list:
        lines.append(f"\n🧑‍💼 <b>HR-менеджеры ({len(hr_list)}):</b>")
        for uid in hr_list:
            label = await _user_label(message.bot, uid)
            suffix = f" — {escape(label)}" if label else " — (не писал боту)"
            lines.append(f"  • <code>{uid}</code>{suffix}")
    else:
        lines.append("\n🧑‍💼 <b>HR-менеджеров нет.</b>")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.main_menu(message.from_user.id))


# ── Добавить HR-менеджера ─────────────────────────────────────────────────────

@router.message(lambda m: m.text == "➕ Добавить HR-менеджера")
async def start_add_hr(message: Message, state: FSMContext) -> None:
    if not _admin_only(message):
        await message.answer("⛔ Только для администраторов.")
        return
    await state.set_state(AdminAddHR.waiting_id)
    await message.answer(
        "🔢 Введите <b>Telegram ID</b> нового HR-менеджера:\n\n"
        "💡 Пользователь может узнать свой ID командой /myid",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AdminAddHR.waiting_id)
async def process_add_hr(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ ID должен быть числом. Попробуйте ещё раз:")
        return

    user_id = int(text)
    added = user_store.add_hr_user(user_id)
    await state.clear()

    if added:
        await message.answer(
            f"✅ HR-менеджер <code>{user_id}</code> добавлен.\n"
            "Теперь он имеет доступ к HR-функционалу бота.",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )
    elif user_store.is_admin(user_id):
        await message.answer(
            f"ℹ️ Пользователь <code>{user_id}</code> является администратором — у него уже есть полный доступ.",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"ℹ️ Пользователь <code>{user_id}</code> уже является HR-менеджером.",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )


# ── Удалить HR-менеджера ──────────────────────────────────────────────────────

@router.message(lambda m: m.text == "➖ Удалить HR-менеджера")
async def start_remove_hr(message: Message, state: FSMContext) -> None:
    if not _admin_only(message):
        await message.answer("⛔ Только для администраторов.")
        return

    hr_list = user_store.list_hr_users()
    if not hr_list:
        await message.answer(
            "ℹ️ Нет HR-менеджеров для удаления.",
            reply_markup=kb.main_menu(message.from_user.id),
        )
        return

    await state.set_state(AdminRemoveHR.waiting_id)
    lines = ["🧑‍💼 <b>HR-менеджеры:</b>\n"]
    for uid in hr_list:
        lines.append(f"  • <code>{uid}</code>")
    lines.append("\n🔢 Введите ID для удаления:")

    await message.answer(
        "\n".join(lines),
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AdminRemoveHR.waiting_id)
async def process_remove_hr(message: Message, state: FSMContext) -> None:
    if message.text == "🚫 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=kb.main_menu(message.from_user.id))
        return

    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ ID должен быть числом. Попробуйте ещё раз:")
        return

    user_id = int(text)
    removed = user_store.remove_hr_user(user_id)
    await state.clear()

    if removed:
        await message.answer(
            f"✅ HR-менеджер <code>{user_id}</code> удалён.",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )
    elif user_store.is_admin(user_id):
        await message.answer(
            f"⛔ Нельзя удалить администратора <code>{user_id}</code>.",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⚠️ Пользователь <code>{user_id}</code> не найден в списке HR-менеджеров.",
            reply_markup=kb.main_menu(message.from_user.id),
            parse_mode="HTML",
        )
