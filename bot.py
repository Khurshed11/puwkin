import asyncio
import logging
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.db import create_tables
from database.settings_store import get_setting

# Импорт роутеров
from handlers import user, catalog, size_helper, cart, admin, extras

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def load_dynamic_settings() -> None:
    """Подгружает настройки доставки из БД в объект settings при старте."""
    min_days = await get_setting("delivery_min_days")
    max_days = await get_setting("delivery_max_days")
    if min_days and min_days.isdigit():
        settings.DELIVERY_MIN_DAYS = int(min_days)
    if max_days and max_days.isdigit():
        settings.DELIVERY_MAX_DAYS = int(max_days)


class IPv4Session(AiohttpSession):
    """
    AiohttpSession с принудительным IPv4.

    У многих провайдеров DNS отдаёт IPv6-адрес api.telegram.org, но реально
    маршрутизирует только IPv4. Тогда aiohttp пытается подключиться по IPv6 и
    падает с 'getaddrinfo failed' и случайными обрывами. family=AF_INET
    заставляет соединение всегда идти по IPv4 — это убирает обрывы.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET


def build_session() -> AiohttpSession:
    """Сессия с keep-alive и принудительным IPv4."""
    return IPv4Session()


async def main() -> None:
    if not settings.BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env и заполните его."
        )

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=build_session(),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Инициализация БД и настроек
    await create_tables()
    await load_dynamic_settings()
    logger.info("База данных готова. Срок доставки: %s", settings.delivery_range)

    # Порядок важен: admin раньше user, чтобы /admin не перехватывался.
    # extras последним — его message-хендлеры (поиск/отзыв) срабатывают
    # только в своих FSM-состояниях и не мешают базовому меню.
    dp.include_router(admin.router)
    dp.include_router(user.router)
    dp.include_router(catalog.router)
    dp.include_router(size_helper.router)
    dp.include_router(cart.router)
    dp.include_router(extras.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
