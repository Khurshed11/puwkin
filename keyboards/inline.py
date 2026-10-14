from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import Category, Product

# Сколько товаров показывать на одной странице каталога
PRODUCTS_PER_PAGE = 5


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В главное меню", callback_data="menu:main")
    return builder.as_markup()


def categories_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    """Список категорий + кнопка 'Назад'."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat:{cat.id}:0")
    builder.button(text="⬅️ В главное меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def products_kb(
    category_id: int,
    products: list[Product],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Список товаров категории (компактный вид) с пагинацией."""
    builder = InlineKeyboardBuilder()
    for prod in products:
        # prod: — точка входа: откроется фото-карточка товара в галерее
        builder.button(text=prod.name, callback_data=f"prod:{prod.id}:{page}")
    # Навигация (остаёмся в текстовом списке)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=f"catlist:{category_id}:{page - 1}"
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text="➡️", callback_data=f"catlist:{category_id}:{page + 1}"
            )
        )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="🖼 Фото-режим", callback_data=f"cat:{category_id}:0"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К категориям", callback_data="menu:catalog"
        )
    )
    return builder.as_markup()


def gallery_card_kb(
    product_id: int,
    category_id: int,
    idx: int,
    total: int,
    is_fav: bool = False,
    n_photos: int = 0,
    photo_idx: int = 0,
) -> InlineKeyboardMarkup:
    """
    Карточка товара в режиме галереи: фото + стрелки листания
    по товарам категории + покупка и избранное.
    """
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🛒 В корзину",
            callback_data=f"addcart:{product_id}:{category_id}:{idx}",
        ),
        InlineKeyboardButton(
            text="📐 Подобрать размер",
            callback_data=f"size:{product_id}",
        ),
    )
    fav_btn = InlineKeyboardButton(
        text="💔 Убрать" if is_fav else "❤️ В избранное",
        callback_data=f"fav:{product_id}:{category_id}:{idx}",
    )
    if n_photos > 1:
        nxt = (photo_idx + 1) % n_photos
        b.row(
            fav_btn,
            InlineKeyboardButton(
                text=f"📷 Фото {photo_idx + 1}/{n_photos}",
                callback_data=f"ph:{product_id}:{category_id}:{idx}:{nxt}",
            ),
        )
    else:
        b.row(fav_btn)
    # Стрелки листания по товарам
    nav: list[InlineKeyboardButton] = []
    if idx > 0:
        nav.append(
            InlineKeyboardButton(
                text="◀️", callback_data=f"gal:{category_id}:{idx - 1}"
            )
        )
    nav.append(
        InlineKeyboardButton(text=f"{idx + 1} из {total}", callback_data="noop")
    )
    if idx < total - 1:
        nav.append(
            InlineKeyboardButton(
                text="▶️", callback_data=f"gal:{category_id}:{idx + 1}"
            )
        )
    b.row(*nav)
    b.row(
        InlineKeyboardButton(
            text="📝 Списком", callback_data=f"catlist:{category_id}:0"
        ),
        InlineKeyboardButton(
            text="⬅️ Категории", callback_data="menu:catalog"
        ),
    )
    return b.as_markup()


def choose_size_kb(product_id: int, category_id: int, page: int) -> InlineKeyboardMarkup:
    """Кнопки выбора типового размера при добавлении в корзину."""
    builder = InlineKeyboardBuilder()
    for size in ["S", "M", "L", "XL", "XXL"]:
        builder.button(
            text=size,
            callback_data=f"pick:{product_id}:{category_id}:{page}:{size}",
        )
    builder.button(
        text="🤷 Не знаю размер",
        callback_data=f"size:{product_id}",
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад", callback_data=f"gal:{category_id}:{page}"
        )
    )
    builder.adjust(5, 1, 1)
    return builder.as_markup()


def cart_kb(has_items: bool) -> InlineKeyboardMarkup:
    """Корзина."""
    builder = InlineKeyboardBuilder()
    if has_items:
        builder.button(text="✅ Оформить заказ", callback_data="checkout:start")
        builder.button(text="🗑 Очистить корзину", callback_data="cart:clear")
    builder.button(text="⬅️ В главное меню", callback_data="menu:main")
    builder.adjust(1)
    return builder.as_markup()


def cart_item_kb(item_id: int) -> InlineKeyboardMarkup:
    """Кнопка удаления конкретной позиции."""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Удалить", callback_data=f"cart:del:{item_id}")
    return builder.as_markup()


def confirm_order_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="order:confirm")
    builder.button(text="❌ Отмена", callback_data="menu:main")
    builder.adjust(2)
    return builder.as_markup()
