from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from config import settings
from database.models import Category, Product, CartItem, Order, OrderItem
from database.db import session_maker
from keyboards.inline import (
    cart_kb,
    confirm_order_kb,
    back_to_menu,
)
from keyboards.reply import cancel_reply_kb, main_reply_kb
from states import Checkout
from handlers.catalog import (
    get_products,
    get_categories,
    edit_card,
    render_gallery_card,
)

router = Router(name="cart")


def _format_cart(items: list[CartItem]) -> tuple[str, float]:
    total = 0.0
    lines = ["🛒 <b>Ваша корзина</b>\n"]
    for i, item in enumerate(items, 1):
        p = item.product
        total += p.price or 0.0
        lines.append(
            f"{i}. <b>{p.name}</b>\n"
            f"   Размер: {item.size}\n"
            f"   Цена: {int(p.price)} {settings.CURRENCY}\n"
            f"   Доставка: {p.delivery_price}"
        )
    lines.append(f"\n💰 <b>Итого за товары:</b> {int(total)} {settings.CURRENCY}")
    lines.append(f"⏱ Срок доставки: {settings.delivery_range}")
    return "\n".join(lines), total


async def _get_cart_items(session, user_id: int) -> list[CartItem]:
    result = await session.execute(
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .order_by(CartItem.id)
        .options(selectinload(CartItem.product))
    )
    return list(result.scalars().all())


@router.message(F.text == "🛒 Корзина")
async def msg_cart(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        items = await _get_cart_items(session, message.from_user.id)
    if not items:
        await message.answer(
            "🛒 Ваша корзина пуста.\n\nЗагляните в каталог, чтобы выбрать одежду!",
            reply_markup=cart_kb(False),
        )
        return
    text, _ = _format_cart(items)
    await message.answer(text, reply_markup=cart_kb(True))


@router.callback_query(F.data == "menu:cart")
async def show_cart(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        items = await _get_cart_items(session, callback.from_user.id)
    if not items:
        await callback.message.edit_text(
            "🛒 Ваша корзина пуста.\n\nЗагляните в каталог, чтобы выбрать одежду!",
            reply_markup=cart_kb(False),
        )
        await callback.answer()
        return
    text, _ = _format_cart(items)
    await callback.message.edit_text(text, reply_markup=cart_kb(True))
    await callback.answer()


@router.callback_query(F.data.startswith("addcart:"))
async def add_to_cart(callback: CallbackQuery) -> None:
    _, prod_id_str, cat_id_str, page_str = callback.data.split(":")
    product_id, category_id, page = int(prod_id_str), int(cat_id_str), int(page_str)
    from keyboards.inline import choose_size_kb

    await edit_card(
        callback.message,
        "Выберите размер для добавления в корзину:",
        choose_size_kb(product_id, category_id, page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pick:"))
async def pick_size_to_cart(callback: CallbackQuery) -> None:
    _, prod_id_str, cat_id_str, page_str, size = callback.data.split(":")
    product_id, category_id, page = int(prod_id_str), int(cat_id_str), int(page_str)

    async with session_maker() as session:
        session.add(
            CartItem(user_id=callback.from_user.id, product_id=product_id, size=size)
        )
        await session.commit()

    # Возвращаемся на фото-карточку товара в галерее
    await render_gallery_card(
        callback.bot,
        callback.message,
        callback.from_user.id,
        category_id,
        page,
    )
    await callback.answer("✅ Товар добавлен в корзину!")


@router.callback_query(F.data.startswith("cart:del:"))
async def delete_cart_item(callback: CallbackQuery) -> None:
    item_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        await session.execute(delete(CartItem).where(CartItem.id == item_id))
        await session.commit()
        items = await _get_cart_items(session, callback.from_user.id)
    if not items:
        await callback.message.edit_text("🛒 Корзина пуста.", reply_markup=cart_kb(False))
    else:
        text, _ = _format_cart(items)
        await callback.message.edit_text(text, reply_markup=cart_kb(True))
    await callback.answer("Удалено.")


@router.callback_query(F.data == "cart:clear")
async def clear_cart(callback: CallbackQuery) -> None:
    async with session_maker() as session:
        await session.execute(
            delete(CartItem).where(CartItem.user_id == callback.from_user.id)
        )
        await session.commit()
    await callback.message.edit_text("🛒 Корзина очищена.", reply_markup=cart_kb(False))
    await callback.answer()


# ============ Оформление заказа ============
@router.callback_query(F.data == "checkout:start")
async def start_checkout(callback: CallbackQuery, state: FSMContext) -> None:
    async with session_maker() as session:
        items = await _get_cart_items(session, callback.from_user.id)
    if not items:
        await callback.answer("Корзина пуста.", show_alert=True)
        return
    await state.set_state(Checkout.waiting_phone)
    await callback.message.edit_text(
        "📝 <b>Оформление заказа</b>\n\n"
        f"Срок доставки: <b>{settings.delivery_range}</b> с момента подтверждения.\n\n"
        "Отправьте ваш <b>номер телефона</b> для связи:",
    )
    await callback.bot.send_message(
        callback.message.chat.id, "Введите телефон:", reply_markup=cancel_reply_kb()
    )
    await callback.answer()


@router.message(Checkout.waiting_phone, F.text)
async def checkout_phone(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    if len(phone) < 5:
        await message.answer("Пожалуйста, укажите корректный номер телефона.")
        return
    await state.update_data(phone=phone)
    await state.set_state(Checkout.waiting_address)
    await message.answer(
        "Принято! Теперь отправьте <b>адрес доставки</b> (город, улица, дом / ПВЗ):"
    )


@router.message(Checkout.waiting_address, F.text)
async def checkout_address(message: Message, state: FSMContext) -> None:
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("Пожалуйста, укажите более подробный адрес.")
        return

    data = await state.get_data()
    phone = data.get("phone", "—")

    async with session_maker() as session:
        items = await _get_cart_items(session, message.from_user.id)
        text, total = _format_cart(items)

    await state.update_data(address=address)
    summary = (
        f"{text}\n\n"
        f"📞 Телефон: <b>{phone}</b>\n"
        f"📍 Адрес: <b>{address}</b>\n\n"
        "Всё верно? Подтвердите заказ."
    )
    await message.answer(summary, reply_markup=confirm_order_kb())


@router.callback_query(F.data == "order:confirm")
async def confirm_order(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    phone = data.get("phone", "—")
    address = data.get("address", "—")
    await state.clear()

    async with session_maker() as session:
        items = await _get_cart_items(session, callback.from_user.id)
        if not items:
            await callback.answer("Корзина пуста.", show_alert=True)
            return
        _, total = _format_cart(items)

        order = Order(
            user_id=callback.from_user.id,
            username=callback.from_user.username or "—",
            full_name=callback.from_user.full_name,
            phone=phone,
            address=address,
            total=total,
        )
        session.add(order)
        await session.flush()

        for item in items:
            session.add(
                OrderItem(
                    order_id=order.id,
                    product_name=item.product.name,
                    size=item.size,
                    price=item.product.price or 0.0,
                    delivery_price=item.product.delivery_price,
                )
            )
        await session.execute(
            delete(CartItem).where(CartItem.user_id == callback.from_user.id)
        )
        # Авто-подтверждение, если включено в настройках
        if settings.AUTO_CONFIRM_ORDERS:
            order.status = "confirmed"
        await session.commit()
        order_id = order.id

    if settings.AUTO_CONFIRM_ORDERS:
        # Менеджеру ничего делать не нужно — заказ уже подтверждён
        await callback.message.edit_text(
            f"🎉 <b>Заказ №{order_id} оформлен и подтверждён!</b>\n\n"
            f"⏱ Срок доставки: <b>{settings.delivery_range}</b> с момента оформления.\n"
            "Мы уже начали собирать ваш заказ. Спасибо за покупку! ❤️",
            reply_markup=back_to_menu(),
        )
        # Просим оценить — бот сам собирает отзывы
        from handlers.extras import rating_kb
        await callback.bot.send_message(
            callback.message.chat.id,
            "Пожалуйста, оцените ваш опыт заказа:",
            reply_markup=rating_kb(order_id),
        )
        notify_status = "✅ Авто-подтверждён"
    else:
        await callback.message.edit_text(
            f"🎉 <b>Заказ №{order_id} оформлен!</b>\n\n"
            f"⏱ Срок доставки: <b>{settings.delivery_range}</b> с момента подтверждения.\n"
            "Менеджер скоро свяжется с вами для подтверждения.\n\n"
            "Спасибо за покупку! ❤️",
            reply_markup=back_to_menu(),
        )
        notify_status = "🆕 Ожидает подтверждения"

    notify = (
        f"🔔 <b>Новый заказ №{order_id}</b> ({notify_status})\n\n"
        f"👤 {callback.from_user.full_name} (@{callback.from_user.username or '—'})\n"
        f"🆔 {callback.from_user.id}\n"
        f"📞 Телефон: {phone}\n"
        f"📍 Адрес: {address}\n\n"
        f"💰 Сумма товаров: {int(total)} {settings.CURRENCY}\n"
        f"⏱ Срок: {settings.delivery_range}"
    )
    for admin_id in settings.admin_ids:
        try:
            await callback.bot.send_message(admin_id, notify)
        except Exception:
            pass
    # Возвращаем главную панель кнопок внизу
    await callback.bot.send_message(
        callback.message.chat.id,
        "🏠 <b>Главное меню</b>",
        reply_markup=main_reply_kb(is_admin=callback.from_user.id in settings.admin_ids),
    )
    await callback.answer()


# ============================================================
#  МОИ ЗАКАЗЫ (клиент)
# ============================================================
@router.callback_query(F.data == "menu:orders")
async def show_my_orders(callback: CallbackQuery) -> None:
    async with session_maker() as session:
        orders = list(
            (
                await session.execute(
                    select(Order)
                    .options(selectinload(Order.items))
                    .where(Order.user_id == callback.from_user.id)
                    .order_by(Order.id.desc())
                )
            ).unique().scalars().all()
        )
    if not orders:
        await callback.message.edit_text(
            "📦 У вас пока нет заказов.\n\nОформите первый из корзины!",
            reply_markup=back_to_menu(),
        )
        await callback.answer()
        return

    status_map = {"new": "🆕 Ожидает подтверждения", "confirmed": "✅ Подтверждён",
                  "done": "✔️ Выполнен"}
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    lines = ["📦 <b>Ваши заказы</b>\n"]
    b = InlineKeyboardBuilder()
    for o in orders:
        lines.append(
            f"<b>Заказ №{o.id}</b> — {status_map.get(o.status, o.status)}\n"
            f"💰 {int(o.total)} {settings.CURRENCY} | "
            f"⏱ {settings.delivery_range}\n"
        )
        for it in o.items:
            lines.append(f"   • {it.product_name} — {it.size}")
        lines.append("")
        b.button(text=f"🔁 Повторить №{o.id}", callback_data=f"repeat:{o.id}")
    b.button(text="⬅️ В главное меню", callback_data="menu:main")
    b.adjust(1)
    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()

