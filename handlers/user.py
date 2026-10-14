from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from config import settings
from database.models import User
from database.db import session_maker
from keyboards.reply import main_reply_kb

router = Router(name="user")

MANAGER_CONTACT = f"Ваш менеджер: {settings.MANAGER_USERNAME}\n\nНапишите ему напрямую — ответит в течение нескольких минут и поможет с размером, оплатой и доставкой."


async def register_user(message: Message) -> None:
    """Сохраняет пользователя в базу (для рассылки и статистики)."""
    async with session_maker() as session:
        exists = await session.scalar(
            select(User).where(User.user_id == message.from_user.id)
        )
        if not exists:
            session.add(
                User(
                    user_id=message.from_user.id,
                    username=message.from_user.username or "—",
                    full_name=message.from_user.full_name,
                )
            )
            await session.commit()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await register_user(message)
    is_admin = message.from_user.id in settings.admin_ids
    await message.answer(
        f"👋 Добро пожаловать в наш магазин мужской одежды, {message.from_user.full_name}!\n\n"
        "Здесь вы найдёте стильные вещи с доставкой прямо до двери.\n\n"
        f"⏱ Срок доставки: <b>{settings.delivery_range}</b>\n\n"
        "Выберите раздел на панели кнопок внизу 👇",
        reply_markup=main_reply_kb(is_admin=is_admin),
    )


@router.message(Command("help"))
@router.message(F.text == "🏠 Главное меню")
async def cmd_menu(message: Message) -> None:
    await message.answer(
        "🏠 <b>Главное меню</b>\n\nВыберите раздел на панели кнопок внизу 👇",
        reply_markup=main_reply_kb(is_admin=message.from_user.id in settings.admin_ids),
    )


@router.message(F.text == "❌ Отмена")
async def msg_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Действие отменено.\n\n🏠 <b>Главное меню</b>",
        reply_markup=main_reply_kb(is_admin=message.from_user.id in settings.admin_ids),
    )


@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback, state) -> None:
    await state.clear()
    # Убираем текущую карточку (фото или текст) и возвращаем панель вниз
    try:
        if callback.message.photo:
            await callback.message.delete()
        else:
            await callback.message.edit_text("🏠 <b>Главное меню</b>")
    except Exception:
        pass
    await callback.message.answer(
        "Выберите раздел на панели кнопок внизу 👇",
        reply_markup=main_reply_kb(is_admin=callback.from_user.id in settings.admin_ids),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:delivery")
async def cb_delivery(callback) -> None:
    await callback.message.edit_text(_delivery_text())
    await callback.answer()


@router.message(F.text == "🚚 Доставка")
async def msg_delivery(message: Message) -> None:
    await message.answer(_delivery_text())


def _delivery_text() -> str:
    return (
        "🚚 <b>Условия доставки и оплаты</b>\n\n"
        f"⏱ <b>Срок доставки:</b> {settings.delivery_range}\n"
        "(считается со дня подтверждения заказа)\n\n"
        "💰 <b>Оплата:</b> при получении (наличные/перевод) "
        "или предоплата на карту — по договорённости с менеджером.\n\n"
        "📦 Доставка осуществляется курьером до двери / в пункт выдачи.\n\n"
        "❓ По всем вопросам — кнопка «Связь с менеджером»."
    )


@router.callback_query(F.data == "menu:manager")
@router.message(F.text == "💬 Менеджер")
async def show_manager(event, bot=None) -> None:
    from keyboards.inline import back_to_menu

    if hasattr(event, "message"):  # callback
        await event.message.edit_text(MANAGER_CONTACT, reply_markup=back_to_menu())
        await event.answer()
    else:  # message
        await event.answer(MANAGER_CONTACT, reply_markup=back_to_menu())
