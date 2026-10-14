from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_reply_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Постоянная reply-клавиатура под полем ввода."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="🏠 Главное меню")
    builder.button(text="👔 Каталог")
    builder.button(text="🔍 Поиск")
    builder.button(text="📐 Подбор размера")
    builder.button(text="🚚 Доставка")
    builder.button(text="❓ Вопросы")
    builder.button(text="🛒 Корзина")
    builder.button(text="❤️ Избранное")
    builder.button(text="💬 Менеджер")
    if is_admin:
        builder.button(text="⚙️ Админ-панель")
        builder.adjust(2, 2, 2, 2, 1)  # 9 кнопок
    else:
        builder.adjust(2, 2, 2, 2)     # 8 кнопок
    return builder.as_markup(resize_keyboard=True)


def cancel_reply_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отмена")
    return builder.as_markup(resize_keyboard=True)


remove_kb = ReplyKeyboardRemove()
