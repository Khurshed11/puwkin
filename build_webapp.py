"""
Сборка статичного веб-каталога (Telegram Mini App на GitHub Pages).

Читает shop.db, скачивает фото товаров через Bot API (file_id → файл),
кладёт их в webapp/photos/ и пишет webapp/catalog.json — то, что видит
мини-апп в Telegram.

Запуск:
    & C:/Users/user/AppData/Local/Microsoft/WindowsApps/python3.13.exe build_webapp.py

На GitHub Actions запускается workflow'ом webapp.yml (фото качаются
токеном из секрета BOT_TOKEN — в репозиторий он не попадает).
"""
import asyncio
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import aiohttp
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot import build_session
from config import settings
from database.db import create_tables, session_maker
from database.models import Product

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "webapp"
PHOTOS = OUT / "photos"
SHOP_NAME = "Мужская одежда — стиль каждый день"


async def main() -> None:
    await create_tables()

    PHOTOS.mkdir(parents=True, exist_ok=True)
    for old in PHOTOS.iterdir():  # чистим, чтобы убрать фото удалённых товаров
        if old.is_file():
            old.unlink()

    async with session_maker() as session:
        products = list(
            (
                await session.execute(
                    select(Product)
                    .options(selectinload(Product.category))
                    .where(Product.is_active.is_(True))
                    .order_by(Product.id)
                )
            )
            .scalars()
        )

        categories: list[dict] = []
        seen: set[int] = set()
        for p in products:
            if p.category and p.category.id not in seen:
                seen.add(p.category.id)
                categories.append(
                    {"id": p.category.id, "name": p.category.name}
                )

        # Бот нужен только для file_id → файл
        bot: Bot | None = None
        bot_username = "shop"
        if settings.BOT_TOKEN:
            bot = Bot(settings.BOT_TOKEN, session=build_session())
            me = await bot.get_me()
            bot_username = me.username
        else:
            print("⚠️ BOT_TOKEN не задан — фото не будут скачаны")

        items: list[dict] = []
        n_files = 0
        async with aiohttp.ClientSession() as http:
            for p in products:
                urls: list[str] = []
                if bot is not None:
                    for i, file_id in enumerate(p.photos[:6]):
                        try:
                            f = await bot.get_file(file_id)
                            if not f.file_path:
                                raise RuntimeError("пустой file_path")
                            url = (
                                "https://api.telegram.org/file/bot"
                                f"{settings.BOT_TOKEN}/{f.file_path}"
                            )
                            async with http.get(url) as resp:
                                if resp.status != 200:
                                    raise RuntimeError(f"HTTP {resp.status}")
                                blob = await resp.read()
                            ext = Path(f.file_path).suffix or ".jpg"
                            name = f"{p.id}_{i}{ext}"
                            (PHOTOS / name).write_bytes(blob)
                            urls.append(f"photos/{name}")
                            n_files += 1
                        except Exception as e:
                            print(f"⚠️ {p.name}: фото {i + 1} не скачалось ({e})")
                items.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "category_id": p.category_id,
                        "price": p.price,
                        "delivery_price": p.delivery_price,
                        "description": p.size_chart,
                        "photos": urls,
                        "currency": settings.CURRENCY,
                        "delivery_range": settings.delivery_range,
                    }
                )
                print(f"📦 {p.name}: фото {len(urls)}")

        if bot is not None:
            await bot.session.close()

    payload = {
        "shop": {
            "name": SHOP_NAME,
            "currency": settings.CURRENCY,
            "delivery": settings.delivery_range,
            "bot_url": f"https://t.me/{bot_username}",
        },
        "categories": categories,
        "products": items,
    }
    (OUT / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n✅ Готово: товаров {len(items)}, категорий {len(categories)}, "
          f"файлов фото {n_files}")
    print(f"   → {OUT / 'catalog.json'}")


if __name__ == "__main__":
    asyncio.run(main())