import math

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from sqlalchemy import select

from config import settings
from database.models import Category, Favorite, Product
from database.db import session_maker
from keyboards.inline import (
    categories_kb,
    products_kb,
    gallery_card_kb,
    PRODUCTS_PER_PAGE,
    back_to_menu,
)

router = Router(name="catalog")

# Лимит подписи у Telegram — 1024 символа (оставляем запас)
CAPTION_LIMIT = 1000


async def get_categories(session) -> list[Category]:
    result = await session.execute(select(Category).order_by(Category.id))
    return list(result.scalars().all())


async def get_products(session, category_id: int) -> list[Product]:
    result = await session.execute(
        select(Product)
        .where(Product.category_id == category_id, Product.is_active == True)  # noqa: E712
        .order_by(Product.id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Утилиты для карточек-сообщений (фото и текст)
# ---------------------------------------------------------------------------

async def edit_card(message: Message, text: str, reply_markup=None) -> None:
    """
    Редактирует текущее сообщение-карточку: подпись, если это фото,
    иначе текст. Если редактирование невозможно — удаляет и отправляет
    новое сообщение (используется в корзине, размернике и т.д.).
    """
    try:
        if message.photo:
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)
        return
    except TelegramBadRequest:
        pass
    except Exception:
        pass
    try:
        await message.delete()
    except Exception:
        pass
    await message.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


def format_card(product: Product, n_photos: int = 0, photo_idx: int = 0) -> str:
    """Подпись карточки товара для галереи."""
    price_txt = (
        f"{int(product.price)} {settings.CURRENCY}" if product.price else "Уточняйте"
    )
    lines = [
        f"🏷 <b>{product.name}</b>",
        "",
        f"💵 Цена: <b>{price_txt}</b>",
        f"🚚 Доставка: <b>{product.delivery_price}</b>",
        f"⏱ Срок доставки: <b>{settings.delivery_range}</b>",
    ]
    if product.size_chart:
        chart = product.size_chart.strip()
        if len(chart) > 450:
            chart = chart[:450] + "…"
        lines += ["", f"📐 <b>Размеры / замеры:</b>", chart]
    if n_photos > 1:
        lines += ["", f"📷 Фото {photo_idx + 1} из {n_photos} — листайте кнопкой"]
    return "\n".join(lines)[:CAPTION_LIMIT]


async def render_gallery_card(
    bot, message: Message, user_id: int, category_id: int, idx: int
) -> None:
    """
    Показывает товар из категории как фото-карточку со стрелками ◀️/▶️.
    Фото + подпись + клавиатура — одно сообщение; навигация делается
    edit'ом, поэтому листание быстрое, без отдельных альбомов.
    """
    async with session_maker() as session:
        products = await get_products(session, category_id)
        if not products:
            await edit_card(
                message, "В этой категории пока нет товаров.", back_to_menu()
            )
            return
        idx = max(0, min(idx, len(products) - 1))
        product = products[idx]
        fav = await session.scalar(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.product_id == product.id,
            )
        )

    photos = product.photos
    caption = format_card(product, n_photos=len(photos))
    kb = gallery_card_kb(
        product.id,
        category_id,
        idx,
        len(products),
        is_fav=fav is not None,
        n_photos=len(photos),
    )

    if photos:
        media = InputMediaPhoto(media=photos[0], caption=caption, parse_mode="HTML")
        if message.photo:
            try:
                await message.edit_media(media=media, reply_markup=kb)
                return
            except TelegramBadRequest:
                pass  # не редактируется — пересылаем новым сообщением
        try:
            await message.delete()
        except Exception:
            pass
        await bot.send_photo(
            message.chat.id, photos[0], caption=caption, reply_markup=kb
        )
    else:
        # Товар без фото — запасной режим: текстовая карточка
        if message.photo:
            try:
                await message.delete()
            except Exception:
                pass
            await bot.send_message(message.chat.id, caption, reply_markup=kb)
        else:
            try:
                await message.edit_text(caption, reply_markup=kb)
            except TelegramBadRequest:
                await edit_card(message, caption, kb)


# ---------------------------------------------------------------------------
# Каталог
# ---------------------------------------------------------------------------

@router.message(F.text == "👔 Каталог")
async def msg_catalog(message: Message) -> None:
    async with session_maker() as session:
        categories = await get_categories(session)
    if not categories:
        await message.answer("Каталог пока пуст. Загляните позже!", reply_markup=back_to_menu())
        return
    await message.answer(
        "👔 <b>Каталог одежды</b>\n\n"
        "Выберите категорию — откроется фото-карточка, "
        "листайте товары кнопками ◀️ ▶️ 👇",
        reply_markup=categories_kb(categories),
    )


@router.callback_query(F.data == "menu:catalog")
async def show_categories(callback: CallbackQuery) -> None:
    async with session_maker() as session:
        categories = await get_categories(session)
    if not categories:
        await edit_card(callback.message, "Каталог пока пуст. Загляните позже!", back_to_menu())
        await callback.answer()
        return
    await edit_card(
        callback.message,
        "👔 <b>Каталог одежды</b>\n\nВыберите категорию:",
        categories_kb(categories),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:"))
async def cb_category_gallery(callback: CallbackQuery) -> None:
    """Выбор категории → сразу фото-карточка первого товара."""
    _, cat_id_str, idx_str = callback.data.split(":")
    await render_gallery_card(
        callback.bot,
        callback.message,
        callback.from_user.id,
        int(cat_id_str),
        int(idx_str),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gal:"))
async def cb_gallery_nav(callback: CallbackQuery) -> None:
    """Стрелки ◀️/▶️: листание товарами в пределах категории."""
    _, cat_id_str, idx_str = callback.data.split(":")
    await render_gallery_card(
        callback.bot,
        callback.message,
        callback.from_user.id,
        int(cat_id_str),
        int(idx_str),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prod:"))
async def show_product(callback: CallbackQuery) -> None:
    """
    Точка входа из избранного/поиска/списка: находим позицию товара
    в его категории и открываем его фото-карточку в галерее.
    """
    _, prod_id_str, _back = callback.data.split(":")
    product_id = int(prod_id_str)

    async with session_maker() as session:
        product = await session.get(Product, product_id)
    if not product or not product.is_active:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    async with session_maker() as session:
        products = await get_products(session, product.category_id)
    idx = next((i for i, p in enumerate(products) if p.id == product_id), 0)
    await render_gallery_card(
        callback.bot,
        callback.message,
        callback.from_user.id,
        product.category_id,
        idx,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ph:"))
async def cb_photo_cycle(callback: CallbackQuery) -> None:
    """Кнопка «📷 Фото N/M»: листание фото внутри карточки."""
    _, prod_str, cat_str, idx_str, pidx_str = callback.data.split(":")
    product_id, category_id = int(prod_str), int(cat_str)
    idx, photo_idx = int(idx_str), int(pidx_str)

    async with session_maker() as session:
        product = await session.get(Product, product_id)
        products = await get_products(session, category_id)
        fav = await session.scalar(
            select(Favorite).where(
                Favorite.user_id == callback.from_user.id,
                Favorite.product_id == product_id,
            )
        )

    photos = product.photos if product else []
    if not photos:
        await callback.answer("Фото пока нет.", show_alert=True)
        return
    photo_idx %= len(photos)

    caption = format_card(product, n_photos=len(photos), photo_idx=photo_idx)
    media = InputMediaPhoto(media=photos[photo_idx], caption=caption, parse_mode="HTML")
    kb = gallery_card_kb(
        product_id,
        category_id,
        idx,
        max(len(products), 1),
        is_fav=fav is not None,
        n_photos=len(photos),
        photo_idx=photo_idx,
    )
    try:
        await callback.message.edit_media(media=media, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer(f"📷 Фото {photo_idx + 1}/{len(photos)}")


@router.callback_query(F.data.startswith("catlist:"))
async def cb_category_list(callback: CallbackQuery) -> None:
    """Текстовый список товаров (кнопка «📝 Списком») с пагинацией."""
    _, cat_id_str, page_str = callback.data.split(":")
    category_id, page = int(cat_id_str), int(page_str)

    async with session_maker() as session:
        products = await get_products(session, category_id)
        category = await session.get(Category, category_id)

    if not products:
        await edit_card(
            callback.message, "В этой категории пока нет товаров.", back_to_menu()
        )
        await callback.answer()
        return

    total_pages = math.ceil(len(products) / PRODUCTS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    chunk = products[page * PRODUCTS_PER_PAGE:(page + 1) * PRODUCTS_PER_PAGE]

    await edit_card(
        callback.message,
        f"<b>{category.name}</b>\n\nСтраница {page + 1} из {total_pages}\n"
        "Выберите товар:",
        products_kb(category_id, chunk, page, total_pages),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    """Счётчик «N из M» — визуальный, без действия."""
    await callback.answer()
