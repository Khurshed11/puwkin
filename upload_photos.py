"""
Демо-фотографии для каталога.

Генерирует стильные плашки с названием товара (Pillow), отправляет их
администратору через бота и сохраняет file_id в карточки товаров —
каталог сразу начинает отображаться с фото в режиме галереи.

Запуск:
    python upload_photos.py            # только товары без фото
    python upload_photos.py --force    # перегенерировать все фото

Позже фото можно заменить в админ-панели («📷 Фото») настоящими
снимками — file_id сохранится в ту же колонку.
"""
import asyncio
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot import build_session
from config import settings
from database.db import create_tables, session_maker
from database.models import Product

W = H = 1000
TMP_DIR = Path("media_tmp")

# Палитра по ключевым словам в названии категории
PALETTES = [
    (["верх", "курт", "пухов", "ветров", "бомбер"], (28, 32, 48), (61, 74, 111)),
    (["худи", "свитш", "флис"], (34, 28, 44), (94, 63, 120)),
    (["брюк", "джин", "джогг", "карго"], (22, 38, 36), (45, 92, 82)),
    (["футб", "лонгсл", "футбол"], (44, 30, 30), (122, 64, 64)),
    (["аксесс", "кепк", "ремень", "шапк"], (38, 36, 24), (108, 96, 48)),
]
FALLBACK = ((25, 30, 45), (58, 70, 105))


def _colors(category_name: str) -> tuple[tuple, tuple]:
    low = (category_name or "").lower()
    for keys, c1, c2 in PALETTES:
        if any(k in low for k in keys):
            return c1, c2
    return FALLBACK


def _font(size: int, bold: bool = False):
    names = ["segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"] if bold \
        else ["segoeui.ttf", "arial.ttf"]
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _gradient(c1: tuple, c2: tuple) -> Image.Image:
    """Вертикальный градиент: столбец 1px → растягивание (быстро)."""
    strip = Image.new("RGB", (1, H))
    draw = ImageDraw.Draw(strip)
    for y in range(H):
        t = y / (H - 1)
        draw.point((0, y), fill=(
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        ))
    return strip.resize((W, H))


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_card(name: str, category: str) -> Image.Image:
    c1, c2 = _colors(category)
    img = _gradient(c1, c2)
    draw = ImageDraw.Draw(img)

    # Декоративная рамка
    draw.rounded_rectangle([46, 46, W - 46, H - 46], radius=44,
                           outline=(255, 255, 255), width=2)

    # Категория сверху
    f_cat = _font(44, bold=True)
    draw.text((W / 2, 140), (category or "НОВИНКА").upper(),
              font=f_cat, fill=(235, 235, 235), anchor="mm")

    # Название товара по центру
    f_name = _font(84, bold=True)
    lines = _wrap(draw, name, f_name, W - 180)
    y = H / 2 - (len(lines) - 1) * 54
    for line in lines:
        draw.text((W / 2, y), line, font=f_name, fill=(255, 255, 255), anchor="mm")
        y += 108

    # Плашка срока доставки
    f_badge = _font(40, bold=True)
    badge = f"ДОСТАВКА {settings.DELIVERY_MIN_DAYS}-{settings.DELIVERY_MAX_DAYS} ДНЕЙ"
    bw = draw.textlength(badge, font=f_badge)
    bx1, by1 = W / 2 - bw / 2 - 34, H - 230
    bx2, by2 = W / 2 + bw / 2 + 34, H - 150
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=24, fill=(255, 255, 255))
    draw.text((W / 2, (by1 + by2) / 2), badge, font=f_badge,
              fill=(25, 28, 40), anchor="mm")

    # Подпись бренда снизу
    draw.text((W / 2, H - 95), "★ Стильная мужская одежда",
              font=_font(34), fill=(230, 230, 230), anchor="mm")
    return img


async def main() -> None:
    force = "--force" in sys.argv
    if not settings.BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN в .env")
    if not settings.admin_ids:
        raise RuntimeError("Не задан ADMIN_IDS в .env")

    await create_tables()
    bot = Bot(
        settings.BOT_TOKEN,
        session=build_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    TMP_DIR.mkdir(exist_ok=True)
    admin_id = settings.admin_ids[0]

    done = skipped = 0
    async with session_maker() as session:
        products = list(
            (
                await session.execute(
                    select(Product)
                    .options(selectinload(Product.category))
                    .order_by(Product.id)
                )
            )
            .scalars().all()
        )
        for p in products:
            if p.photos and not force:
                skipped += 1
                continue
            cat_name = p.category.name if p.category else ""
            path = TMP_DIR / f"product_{p.id}.jpg"
            make_card(p.name, cat_name).save(path, "JPEG", quality=90)

            msg = await bot.send_photo(
                chat_id=admin_id,
                photo=FSInputFile(path),
                caption=f"🖼 Демо-фото для каталога: <b>{p.name}</b>",
            )
            p.photos = [max(msg.photo, key=lambda ph: ph.width).file_id]
            done += 1
            print(f"✅ {p.name} — photo_id сохранён")

        await session.commit()

    await bot.session.close()
    print(f"\nГотово! Загружено: {done}, пропущено (уже с фото): {skipped}")
    print("Фото отправлены вам в ЛС — откройте бота и посмотрите каталог.")


if __name__ == "__main__":
    asyncio.run(main())
