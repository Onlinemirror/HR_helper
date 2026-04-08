"""Общие команды: /start, отмена из любого состояния."""
from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import keyboards as kb

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"👋 Добро пожаловать, {message.from_user.first_name}!\n"
        "Выберите действие в меню ниже.",
        reply_markup=kb.main_menu(),
    )


@router.message(StateFilter("*"), lambda m: m.text == "🚫 Отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного действия.", reply_markup=kb.main_menu())
        return
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=kb.main_menu())
