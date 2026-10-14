"""
Наполнитель каталога примерами товаров.

Запуск (Python 3.13):
    & C:/Users/user/AppData/Local/Microsoft/WindowsApps/python3.13.exe seed_products.py

Скрипт идемпотентный: если категория уже есть — не дублирует её.
Товары создаются заново при каждом запуске (старые примеры удаляются).
"""
import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from sqlalchemy import select, delete

from database.db import create_tables, session_maker
from database.models import Category, Product, CartItem, OrderItem, Order

# Категории и товары. size_chart — в формате, который понимает «Подбор размера».
CATALOG = {
    "Верхняя одежда": [
        ("Куртка-бомбер Aero", 2500, "500",
         "Лёгкая куртка-бомбер из плотного текстиля. Утеплитель держит тепло, "
         "не добавляя объёма. Подходит прохладными вечерами."),
        ("Пуховик Nord", 3900, "Бесплатно",
         "Зимний пуховит с Synthepon-наполнителем. Стеганые линии, "
         "высокий воротник, два глубоких кармана."),
        ("Ветровка Storm", 1800, "500",
         "Ветро- и влагозащитная куртка. Компактно складывается, "
         "удобна в межсезонье и для активного отдыха."),
    ],
    "Худи/Свитшоты": [
        ("Оверсайз худи Heavy", 1500, "500",
         "Плотное оверсайз-худи из трёхнитки с начёсом. Свободный крой, "
         "капюшон на шнурке, флис внутри."),
        ("Свитшот базовый Classic", 1200, "500",
         "Базовый свитшот прямого кроя. Мягкая ткань, резинки по низу "
         "и рукавам не растягиваются."),
        ("Зип-худи Urban", 1700, "500",
         "Худи на молнии с карманом-кенгуру. Универсальный крой, "
         "хорошо сочетается с джинсами и joggers."),
    ],
    "Брюки/Джинсы": [
        ("Джинсы прямые Slim Fit", 1600, "500",
         "Классические джинсы прямого кроя. Плотный деним, средняя "
         "посадка, не теряют форму после стирки."),
        ("Джоггеры Comfort", 1300, "500",
         "Спортивные джоггеры с эластичным поясом и манжетами. "
         "Мягкий футер, удобны каждый день."),
        ("Карго Utility", 1800, "500",
         "Брюки карго с накладными карманами. Прочный хлопок, "
         "свободный крой в стиле утилитарный."),
    ],
    "Футболки": [
        ("Футболка Essential", 700, "Бесплатно",
         "Базовая футболка из плотного хлопка. Прямой крой, "
         "усиленная горловина."),
        ("Футболка Oversize Print", 850, "Бесплатно",
         "Оверсайз-футболка с минималистичным принтом. "
         "Свободная посадка, плотная ткань 220 г/м²."),
        ("Лонгслив Basic", 950, "Бесплатно",
         "Лонгслив с длинным рукавом. Подходит для прохладной погоды, "
         "хорошо держит форму."),
    ],
    "Аксессуары": [
        ("Кепка Classic", 500, "Бесплатно",
         "Бейсболка с жёсткой тульёй и регулируемой застёжкой. "
         "Универсальный крой."),
        ("Ремень кожаный", 800, "Бесплатно",
         "Ремень из искусственной кожи с металлической пряжкой. "
         "Базовая классика."),
        ("Шапка Winter", 600, "Бесплатно",
         "Тёплая вязаная шапка с флисовой подкладкой. "
         "Комфортно сидит, не колется."),
    ],
}

# Универсальная мужская размерная сетка (по категории можно менять)
SIZE_CHART_DEFAULT = (
    "Размеры: S, M, L, XL, XXL\n"
    "Цвета: Чёрный, Графит, Хаки\n"
    "Замеры (Рост/Вес): S (165-172см, 55-66кг), M (172-178см, 66-75кг), "
    "L (178-184см, 75-85кг), XL (184-190см, 85-95кг), XXL (190-198см, 95-108кг)"
)


async def seed():
    await create_tables()

    async with session_maker() as session:
        # Чистим старые примеры (сначала зависимые записи)
        for model in (CartItem, OrderItem, Order):
            await session.execute(delete(model))
        await session.execute(delete(Product))
        await session.execute(delete(Category))
        await session.commit()

        total_products = 0
        for cat_name, products in CATALOG.items():
            # Категория создаётся, если ещё нет
            category = await session.scalar(
                select(Category).where(Category.name == cat_name)
            )
            if not category:
                category = Category(name=cat_name)
                session.add(category)
                await session.flush()

            for name, price, delivery, desc in products:
                # Описание дописываем в начало размерной сетки
                chart = f"{desc}\n\n{SIZE_CHART_DEFAULT}"
                product = Product(
                    category_id=category.id,
                    name=name,
                    price=float(price),
                    delivery_price=delivery,
                    size_chart=chart,
                )
                product.photos = []  # фото добавите через админку
                session.add(product)
                total_products += 1

        await session.commit()

    print(f"Готово! Категорий: {len(CATALOG)}, товаров: {total_products}")
    print("Откройте бота -> 'Каталог одежды', чтобы проверить.")


if __name__ == "__main__":
    asyncio.run(seed())
