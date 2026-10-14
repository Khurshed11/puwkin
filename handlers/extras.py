"""
Расширения и автоматизация магазина:
- ❓ FAQ (бот сам отвечает на частые вопросы)
- 🔍 Поиск по каталогу
- 🔁 Повторить заказ
- ⭐ Отзывы
- 🎟 Промокоды (применяются автоматически)
Менеджеру почти ничего не нужно делать вручную.
"""
import math

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from config import settings
from database.models import (
    Product, Order, OrderItem, CartItem, Promo, Review, User, Favorite,
)
from database.db import session_maker
from keyboards.inline import back_to_menu, cart_kb
from keyboards.reply import cancel_reply_kb, main_reply_kb
from states import Search, ReviewFSM

router = Router(name="extras")


def _main_kb(message: Message):
    return main_reply_kb(is_admin=message.from_user.id in settings.admin_ids)


async def _is_favorite(session, user_id: int, product_id: int) -> bool:
    fav = await session.scalar(
        select(Favorite).where(
            Favorite.user_id == user_id, Favorite.product_id == product_id
        )
    )
    return fav is not None


# ============================================================
#  ИЗБРАННОЕ (Wishlist)
# ============================================================
@router.callback_query(F.data.startswith("fav:"))
async def toggle_favorite(callback: CallbackQuery) -> None:
    _, prod_id_str, cat_id_str, page_str = callback.data.split(":")
    product_id, category_id, page = int(prod_id_str), int(cat_id_str), int(page_str)

    async with session_maker() as session:
        product = await session.get(Product, product_id)
        fav = await session.scalar(
            select(Favorite).where(
                Favorite.user_id == callback.from_user.id,
                Favorite.product_id == product_id,
            )
        )
        if fav:
            await session.delete(fav)
            added = False
        else:
            session.add(
                Favorite(user_id=callback.from_user.id, product_id=product_id)
            )
            added = True
        await session.commit()

    await callback.answer(
        "❤️ Добавлено в избранное!" if added else "💔 Удалено из избранного."
    )
    # Перерисовываем клавиатуру карточки-галереи с обновлённой кнопкой
    if product:
        try:
            from handlers.catalog import get_products
            from keyboards.inline import gallery_card_kb

            async with session_maker() as session:
                products = await get_products(session, category_id)
            idx = next(
                (i for i, p in enumerate(products) if p.id == product_id), page
            )
            await callback.message.edit_reply_markup(
                reply_markup=gallery_card_kb(
                    product_id,
                    category_id,
                    idx,
                    max(len(products), 1),
                    is_fav=added,
                    n_photos=len(product.photos),
                )
            )
        except Exception:
            pass


@router.message(F.text == "❤️ Избранное")
async def msg_favorites(message: Message) -> None:
    async with session_maker() as session:
        favs = list(
            (
                await session.execute(
                    select(Favorite)
                    .where(Favorite.user_id == message.from_user.id)
                    .order_by(Favorite.id.desc())
                )
            ).unique().scalars().all()
        )

    if not favs:
        await message.answer(
            "❤️ <b>Избранное</b>\n\n"
            "Пока пусто. Нажмите «❤️ В избранное» в карточке товара, "
            "чтобы сохранить его сюда.",
            reply_markup=_main_kb(message),
        )
        return

    b = InlineKeyboardBuilder()
    for f in favs:
        p = f.product
        if p:
            b.button(text=f"❤️ {p.name}", callback_data=f"prod:{p.id}:0")
    b.button(text="🗑 Очистить избранное", callback_data="fav:clear")
    b.button(text="⬅️ В главное меню", callback_data="menu:main")
    b.adjust(1)
    await message.answer(
        f"❤️ <b>Избранное</b>\n\nСохранённых товаров: <b>{len(favs)}</b>\n"
        "Выберите, чтобы открыть:",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "fav:clear")
async def clear_favorites(callback: CallbackQuery) -> None:
    async with session_maker() as session:
        await session.execute(
            delete(Favorite).where(Favorite.user_id == callback.from_user.id)
        )
        await session.commit()
    await callback.message.edit_text("🗑 Избранное очищено.")
    await callback.answer()



@router.message(F.text == "🔍 Поиск")
async def msg_search(message: Message, state: FSMContext) -> None:
    await state.set_state(Search.waiting_query)
    await message.answer(
        "🔍 Введите часть названия товара для поиска\n"
        "(например: <i>худи</i> или <i>джинсы</i>).",
        reply_markup=cancel_reply_kb(),
    )


@router.message(F.text == "❓ Вопросы")
async def msg_faq(message: Message) -> None:
    await message.answer(
        "❓ <b>Частые вопросы</b>\n\nВыберите вопрос — бот ответит мгновенно:",
        reply_markup=faq_kb(),
    )


# ============================================================
#  ЧАСТЫЕ ВОПРОСЫ (FAQ) — бот отвечает сам
# ============================================================
FAQ_ITEMS = [
    ("⏱ Сколько ждать доставку?", "faq:delivery"),
    ("💰 Как оплатить?", "faq:pay"),
    ("📐 Как выбрать размер?", "faq:size"),
    ("🔄 Можно ли вернуть/обменять?", "faq:return"),
]


def faq_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for text, cb in FAQ_ITEMS:
        b.button(text=text, callback_data=cb)
    b.button(text="💬 Задать вопрос менеджеру", callback_data="faq:ask")
    b.button(text="⬅️ В главное меню", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "menu:faq")
async def show_faq(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❓ <b>Частые вопросы</b>\n\nВыберите вопрос — бот ответит мгновенно:",
        reply_markup=faq_kb(),
    )
    await callback.answer()


FAQ_ANSWERS = {
    "faq:delivery": (
        f"⏱ <b>Срок доставки: {settings.delivery_range}</b>\n\n"
        "Срок считается со дня подтверждения заказа. "
        "Доставка курьером до двери или в пункт выдачи."
    ),
    "faq:pay": (
        "💰 <b>Оплата</b>\n\n"
        "• При получении (наличные/перевод)\n"
        "• Предоплата на карту — по договорённости с менеджером\n\n"
        "Стоимость доставки указана в карточке каждого товара."
    ),
    "faq:size": (
        "📐 <b>Подбор размера</b>\n\n"
        "Нажмите «📐 Подбор размера» в меню или в карточке товара — "
        "бот задаст 2 вопроса (рост и вес) и подберёт размер по сетке товара."
    ),
    "faq:return": (
        "🔄 <b>Возврат и обмен</b>\n\n"
        "Обмен/возврат возможен в течение 14 дней при сохранении товарного вида "
        "и бирок. Подробности — у менеджера."
    ),
}


@router.callback_query(F.data.startswith("faq:"))
async def faq_answer(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data
    if key == "faq:ask":
        await callback.message.edit_text(
            "💬 Напишите ваш вопрос одним сообщением — менеджер получит его и ответит.",
            reply_markup=back_to_menu(),
        )
        await callback.answer()
        return
    answer = FAQ_ANSWERS.get(key, "Информация уточняется.")
    await callback.message.edit_text(answer, reply_markup=faq_kb())
    await callback.answer()


# ============================================================
#  ПОИСК ПО КАТАЛОГУ
# ============================================================
@router.callback_query(F.data == "menu:search")
async def start_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Search.waiting_query)
    await callback.message.edit_text(
        "🔍 Введите часть названия товара для поиска\n"
        "(например: <i>худи</i> или <i>джинсы</i>).",
        reply_markup=back_to_menu(),
    )
    await callback.answer()


@router.message(Search.waiting_query, F.text)
async def process_search(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Слишком короткий запрос. Введите хотя бы 2 символа.")
        return
    await state.clear()

    async with session_maker() as session:
        products = list(
            (
                await session.execute(
                    select(Product)
                    .where(Product.is_active == True, Product.name.ilike(f"%{query}%"))  # noqa: E712
                    .order_by(Product.id)
                    .limit(20)
                )
            ).scalars().all()
        )

    if not products:
        await message.answer(
            f"🔍 По запросу «{query}» ничего не найдено.\n"
            "Попробуйте другое слово или откройте каталог."
        )
        await message.answer("🏠 <b>Главное меню</b>", reply_markup=_main_kb(message))
        return

    b = InlineKeyboardBuilder()
    for p in products:
        b.button(text=p.name, callback_data=f"prod:{p.id}:0")
    b.button(text="⬅️ В главное меню", callback_data="menu:main")
    b.adjust(1)
    await message.answer(
        f"🔍 Найдено товаров: <b>{len(products)}</b>\nВыберите:",
        reply_markup=b.as_markup(),
    )


# ============================================================
#  ПОВТОРИТЬ ЗАКАЗ (из «Мои заказы»)
# ============================================================
@router.callback_query(F.data.startswith("repeat:"))
async def repeat_order(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[1])
    async with session_maker() as session:
        order = await session.get(
            Order, order_id, options=[selectinload(Order.items)]
        )
        if not order or order.user_id != callback.from_user.id:
            await callback.answer("Заказ не найден.", show_alert=True)
            return
        # Находим товары по именам из позиций заказа
        names = [it.product_name for it in order.items]
        added = 0
        for item in order.items:
            product = await session.scalar(
                select(Product).where(Product.name == item.product_name)
            )
            if product:
                session.add(
                    CartItem(user_id=callback.from_user.id,
                             product_id=product.id, size=item.size)
                )
                added += 1
        await session.commit()

    await callback.answer()
    await callback.message.edit_text(
        f"🔁 Добавлено в корзину позиций: <b>{added}</b> из {len(names)}.\n"
        "Откройте корзину, чтобы оформить.",
        reply_markup=cart_kb(True),
    )


# ============================================================
#  ОТЗЫВЫ (бот сам просит оценить после заказа)
# ============================================================
def rating_kb(order_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for star in range(1, 6):
        b.button(text="⭐" * star, callback_data=f"rate:{order_id}:{star}")
    b.button(text="Пропустить", callback_data=f"rate:{order_id}:0")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.startswith("rate:"))
async def start_review(callback: CallbackQuery, state: FSMContext) -> None:
    _, order_id_str, star_str = callback.data.split(":")
    star = int(star_str)
    if star == 0:
        await callback.message.edit_text(
            "Спасибо! Будем рады видеть вас снова. ❤️", reply_markup=back_to_menu()
        )
        await callback.answer()
        return
    await state.update_data(review_order=int(order_id_str), review_star=star)
    await state.set_state(ReviewFSM.waiting_text)
    await callback.message.edit_text(
        f"Спасибо за оценку {'⭐' * star}!\n\n"
        "Если хотите — напишите пару слов о товаре/доставке "
        "(или отправьте «-», чтобы пропустить):",
    )
    await callback.answer()


@router.message(ReviewFSM.waiting_text, F.text)
async def save_review(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = data.get("review_order", 0)
    star = data.get("review_star", 5)
    text = "" if message.text.strip() == "-" else message.text.strip()
    await state.clear()

    async with session_maker() as session:
        session.add(
            Review(user_id=message.from_user.id, order_id=order_id,
                   rating=star, text=text)
        )
        await session.commit()

    await message.answer("🙏 Спасибо за отзыв! Он помогает нам становиться лучше.")
    await message.answer("🏠 <b>Главное меню</b>", reply_markup=_main_kb(message))

    # Уведомляем админа об отзыве (чтобы знать о проблемах)
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"⭐ <b>Новый отзыв</b> (заказ №{order_id})\n"
                f"Оценка: {'⭐' * star}\n"
                f"От: {message.from_user.full_name}\n"
                f"Текст: {text or '—'}",
            )
        except Exception:
            pass


# ============================================================
#  ПРОМОКОДЫ — применение автоматически
# ============================================================
async def get_active_promo(code: str) -> Promo | None:
    async with session_maker() as session:
        return await session.scalar(
            select(Promo).where(Promo.code == code.strip().upper(),
                                Promo.is_active == True)  # noqa: E712
        )


async def apply_promo_to_cart(user_id: int, promo: Promo) -> float:
    """Возвращает размер скидки в валюте на текущую корзину."""
    async with session_maker() as session:
        items = list(
            (
                await session.execute(
                    select(CartItem)
                    .where(CartItem.user_id == user_id)
                    .options(selectinload(CartItem.product))
                )
            ).scalars().all()
        )
        total = sum((it.product.price or 0.0) for it in items)
        discount = total * promo.discount_percent / 100.0
        # Увеличиваем счётчик использований
        p = await session.get(Promo, promo.id)
        if p:
            p.used_count += 1
            await session.commit()
        return discount


