from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from config import settings
from database.models import Product
from database.db import session_maker
from handlers.catalog import edit_card
from keyboards.inline import back_to_menu
from keyboards.reply import cancel_reply_kb, main_reply_kb
from states import SizeHelper
from utils.size_parser import recommend_size

router = Router(name="size_helper")


@router.message(F.text == "📐 Подбор размера")
async def msg_menu_size(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SizeHelper.waiting_height)
    await message.answer(
        "📐 <b>Подбор размера</b>\n\n"
        "Отправьте ваш <b>рост в см</b> (например: 178).",
        reply_markup=cancel_reply_kb(),
    )


@router.callback_query(F.data == "menu:size")
async def cb_menu_size(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SizeHelper.waiting_height)
    await callback.message.edit_text(
        "📐 <b>Подбор размера</b>\n\n"
        "Отправьте, пожалуйста, ваш <b>рост в см</b> (например: 178).\n\n"
        "Если хотите прервать — нажмите «Отмена».",
    )
    await callback.bot.send_message(
        callback.message.chat.id, "Введите рост (см):", reply_markup=cancel_reply_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("size:"))
async def cb_size_from_product(callback: CallbackQuery, state: FSMContext) -> None:
    """Подбор размера конкретного товара (сохраняем его id)."""
    product_id = int(callback.data.split(":")[1])
    async with session_maker() as session:
        product = await session.get(Product, product_id)
    if not product:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    await state.update_data(size_product_id=product_id)
    await state.set_state(SizeHelper.waiting_height)
    # edit_card: карточка может быть фото — правим подпись, а не текст
    await edit_card(
        callback.message,
        f"📐 <b>Подбор размера для «{product.name}»</b>\n\n"
        "Отправьте ваш <b>рост в см</b> (например: 178).",
    )
    await callback.bot.send_message(
        callback.message.chat.id, "Введите рост (см):", reply_markup=cancel_reply_kb()
    )
    await callback.answer()


def _parse_number(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


@router.message(SizeHelper.waiting_height, F.text)
async def process_height(message: Message, state: FSMContext) -> None:
    height = _parse_number(message.text)
    if height is None or not (100 <= height <= 250):
        await message.answer("Пожалуйста, введите рост числом в см (например: 178).")
        return
    await state.update_data(height=height)
    await state.set_state(SizeHelper.waiting_weight)
    await message.answer("Отлично! Теперь отправьте ваш <b>вес в кг</b> (например: 74).")


@router.message(SizeHelper.waiting_weight, F.text)
async def process_weight(message: Message, state: FSMContext) -> None:
    weight = _parse_number(message.text)
    if weight is None or not (30 <= weight <= 300):
        await message.answer("Пожалуйста, введите вес числом в кг (например: 74).")
        return

    data = await state.get_data()
    height = data.get("height")
    product_id = data.get("size_product_id")
    await state.clear()

    # Если подбор был для конкретного товара — используем его сетку
    if product_id:
        async with session_maker() as session:
            product = await session.get(Product, product_id)
        size_chart = product.size_chart if product else ""
        title = f"«{product.name}»" if product else "товара"
    else:
        size_chart = _UNIVERSAL_CHART
        title = "стандартной сетки"

    size, note = recommend_size(size_chart, height, weight)
    text = (
        f"📐 <b>Результат подбора размера ({title})</b>\n\n"
        f"Ваши параметры: рост <b>{int(height)} см</b>, вес <b>{int(weight)} кг</b>\n\n"
        f"{note}\n\n"
        f"⏱ Срок доставки: <b>{settings.delivery_range}</b>"
    )
    await message.answer(text)
    # Возвращаем главную панель кнопок внизу
    await message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=main_reply_kb(is_admin=message.from_user.id in settings.admin_ids),
    )


# Универсальная мужская размерная сетка, если клиент подбирает размер из меню
_UNIVERSAL_CHART = (
    "S (165-170см, 55-63кг), M (170-176см, 63-72кг), "
    "L (176-182см, 72-82кг), XL (182-190см, 82-92кг), XXL (190-200см, 92-105кг)"
)
