from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload

from config import settings
from database.models import (
    Category, Product, Order, OrderItem, Setting, User, Promo, Review,
)
from database.db import session_maker
from keyboards.inline import back_to_menu
from states import (
    AddProduct, EditProduct, DeliverySettings, Broadcast, PromoAdmin,
)

router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


# Фильтр: весь роутер админа работает только для админов
router.message.filter(F.from_user.func(lambda u: is_admin(u.id)))
router.callback_query.filter(F.from_user.func(lambda u: is_admin(u.id)))


# Текст-шаблон замеров, который бот присылает админу
SIZE_TEMPLATE = (
    "Скопируйте и заполните (не меняя структуру строк):\n\n"
    "<code>"
    "Размеры: M, L, XL\n"
    "Цвета: Черный, Графит\n"
    "Замеры (Рост/Вес): M (170-175см, 65-72кг), L (175-180см, 73-80кг), XL (180-188см, 81-90кг)"
    "</code>\n\n"
    "Просто замените значения на актуальные и отправьте одним сообщением. "
    "Размерную сетку «Рост/Вес» бот использует для подбора размера покупателям."
)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(admin_menu_text(), reply_markup=admin_main_kb())


@router.message(F.text == "⚙️ Админ-панель")
async def admin_panel_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(admin_menu_text(), reply_markup=admin_main_kb())


def admin_menu_text() -> str:
    return (
        "⚙️ <b>Админ-панель</b>\n\n"
        "Выберите действие с помощью кнопок ниже.\n"
        "Все формы пошаговые — просто отвечайте на вопросы бота."
    )


def admin_main_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить товар", callback_data="admin:add")
    b.button(text="📦 Список товаров", callback_data="admin:products")
    b.button(text="🗂 Управление категориями", callback_data="admin:cats")
    b.button(text="📥 Заказы", callback_data="admin:orders")
    b.button(text="📊 Статистика", callback_data="admin:stats")
    b.button(text="📢 Рассылка", callback_data="admin:broadcast")
    b.button(text="🎟 Промокоды", callback_data="admin:promos")
    b.button(text="⭐ Отзывы", callback_data="admin:reviews")
    b.button(text="🚚 Настройки доставки", callback_data="admin:delivery")
    b.button(text="❌ Закрыть", callback_data="admin:close")
    b.adjust(2, 2, 2, 2, 1, 1)
    return b.as_markup()


@router.callback_query(F.data == "admin:close")
async def admin_close(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.delete()
    await callback.answer("Админ-панель закрыта.")


@router.callback_query(F.data == "admin:menu")
async def admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(admin_menu_text(), reply_markup=admin_main_kb())
    await callback.answer()


# ============================================================
#  УПРАВЛЕНИЕ КАТЕГОРИЯМИ
# ============================================================
from aiogram.fsm.state import State, StatesGroup


class AddCategory(StatesGroup):
    name = State()


@router.callback_query(F.data == "admin:cats")
async def admin_cats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        cats = list(
            (await session.execute(select(Category).order_by(Category.id))).scalars().all()
        )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=f"🗑 {c.name}", callback_data=f"admin:catdel:{c.id}")
    b.button(text="➕ Добавить категорию", callback_data="admin:catadd")
    b.button(text="⬅️ Назад", callback_data="admin:menu")
    b.adjust(1)
    text = "🗂 <b>Категории</b>\n\n"
    text += "\n".join(f"• {c.name}" for c in cats) if cats else "Пока нет категорий."
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "admin:catadd")
async def admin_cat_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCategory.name)
    await callback.message.edit_text(
        "➕ Введите <b>название новой категории</b> (например: «Худи/Свитшоты»):",
        reply_markup=back_to_menu(),
    )
    await callback.answer()


@router.message(AddCategory.name, F.text)
async def admin_cat_save(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое. Попробуйте снова.")
        return
    async with session_maker() as session:
        existing = await session.scalar(select(Category).where(Category.name == name))
        if existing:
            await message.answer("Такая категория уже есть.")
        else:
            session.add(Category(name=name))
            await session.commit()
            await message.answer(f"✅ Категория «{name}» добавлена.")
    await state.clear()
    await message.answer(admin_menu_text(), reply_markup=admin_main_kb())


@router.callback_query(F.data.startswith("admin:catdel:"))
async def admin_cat_del(callback: CallbackQuery) -> None:
    cat_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        await session.execute(delete(Category).where(Category.id == cat_id))
        await session.commit()
    await callback.answer("Категория удалена.")
    # Перерисовываем список категорий (без передачи state)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    async with session_maker() as session:
        cats = list(
            (await session.execute(select(Category).order_by(Category.id))).scalars().all()
        )
    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=f"🗑 {c.name}", callback_data=f"admin:catdel:{c.id}")
    b.button(text="➕ Добавить категорию", callback_data="admin:catadd")
    b.button(text="⬅️ Назад", callback_data="admin:menu")
    b.adjust(1)
    text = "🗂 <b>Категории</b>\n\n"
    text += "\n".join(f"• {c.name}" for c in cats) if cats else "Пока нет категорий."
    await callback.message.edit_text(text, reply_markup=b.as_markup())

# ============================================================
#  ДОБАВЛЕНИЕ ТОВАРА — ПОШАГОВАЯ FSM
# ============================================================
@router.callback_query(F.data == "admin:add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    async with session_maker() as session:
        cats = list(
            (await session.execute(select(Category).order_by(Category.id))).scalars().all()
        )
    if not cats:
        await callback.answer("Сначала создайте категорию!", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c.name, callback_data=f"admin:addcat:{c.id}")
    b.button(text="❌ Отмена", callback_data="admin:menu")
    b.adjust(1)

    await state.set_state(AddProduct.category)
    await callback.message.edit_text(
        "<b>Шаг 1 из 6</b> 🗂\n\nВыберите <b>категорию</b> товара:",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(AddProduct.category, F.data.startswith("admin:addcat:"))
async def admin_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[2])
    await state.update_data(category_id=cat_id)
    await state.set_state(AddProduct.name)
    await callback.message.edit_text(
        "<b>Шаг 2 из 6</b> 🏷\n\nВведите <b>название товара</b>\n"
        "Например: <i>Оверсайз худи Heavy</i>",
    )
    await callback.answer()


@router.message(AddProduct.name, F.text)
async def admin_add_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Слишком короткое название. Введите снова:")
        return
    await state.update_data(name=name, photos=[])
    await state.set_state(AddProduct.photos)
    await message.answer(
        "<b>Шаг 3 из 6</b> 🖼\n\n"
        "Отправьте <b>1 или несколько фото</b> товара (по одному сообщению).\n\n"
        "Когда загрузите все фото — нажмите <b>«Готово»</b>.",
        reply_markup=_photos_done_kb(),
    )


def _photos_done_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="✅ Готово", callback_data="admin:photos_done")
    b.button(text="❌ Отмена", callback_data="admin:menu")
    b.adjust(1)
    return b.as_markup()


@router.message(AddProduct.photos, F.photo)
async def admin_add_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"📸 Фото добавлено (всего: {len(photos)}).\n"
        "Отправьте ещё или нажмите «Готово».",
        reply_markup=_photos_done_kb(),
    )


@router.callback_query(AddProduct.photos, F.data == "admin:photos_done")
async def admin_add_photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("photos"):
        await callback.answer("Добавьте хотя бы одно фото!", show_alert=True)
        return
    await state.set_state(AddProduct.price)
    await callback.message.edit_text(
        "<b>Шаг 4 из 6</b> 💵\n\n"
        "Введите <b>цену товара</b> числом (без текста).\n"
        "Например: <code>1500</code>",
    )
    await callback.answer()


@router.message(AddProduct.price, F.text)
async def admin_add_price(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(" ", "")
    if not raw.isdigit():
        await message.answer("Введите цену <b>числом</b>, например: <code>1500</code>")
        return
    await state.update_data(price=float(raw))
    await state.set_state(AddProduct.delivery_price)
    await message.answer(
        "<b>Шаг 5 из 6</b> 🚚\n\n"
        "Введите <b>стоимость доставки</b> товара.\n"
        "Числом (например: <code>500</code>) или словом <code>Бесплатно</code>.",
    )


@router.message(AddProduct.delivery_price, F.text)
async def admin_add_delivery(message: Message, state: FSMContext) -> None:
    delivery = message.text.strip()
    if len(delivery) < 2:
        await message.answer("Введите стоимость доставки или «Бесплатно».")
        return
    await state.update_data(delivery_price=delivery)
    await state.set_state(AddProduct.size_chart)
    await message.answer(
        "<b>Шаг 6 из 6</b> 📐\n\nПришлите замеры и наличие.\n" + SIZE_TEMPLATE,
    )


@router.message(AddProduct.size_chart, F.text)
async def admin_add_size_chart(message: Message, state: FSMContext) -> None:
    size_chart = message.text.strip()
    if len(size_chart) < 3:
        await message.answer("Заполните замеры по шаблону и отправьте снова.")
        return

    data = await state.get_data()
    async with session_maker() as session:
        product = Product(
            category_id=data["category_id"],
            name=data["name"],
            price=data["price"],
            delivery_price=data["delivery_price"],
            size_chart=size_chart,
        )
        product.photos = data.get("photos", [])
        session.add(product)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Товар «{data['name']}» успешно добавлен!</b>\n\n"
        f"💰 Цена: {int(data['price'])} {settings.CURRENCY}\n"
        f"🚚 Доставка: {data['delivery_price']}\n"
        f"⏱ Срок для покупателя: {settings.delivery_range}\n\n"
        "Товар уже виден в каталоге.",
        reply_markup=admin_main_kb(),
    )



# ============================================================
#  СПИСОК ТОВАРОВ + РЕДАКТИРОВАНИЕ
# ============================================================
@router.callback_query(F.data == "admin:products")
async def admin_products(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        products = list(
            (
                await session.execute(
                    select(Product).options(selectinload(Product.category)).order_by(Product.id)
                )
            ).scalars().all()
        )
    if not products:
        await callback.message.edit_text(
            "Товаров пока нет. Добавьте первый через «➕ Добавить товар».",
            reply_markup=admin_main_kb(),
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    for p in products:
        b.button(text=f"{p.name} — {int(p.price)}{settings.CURRENCY}",
                 callback_data=f"admin:prod:{p.id}")
    b.button(text="⬅️ Назад", callback_data="admin:menu")
    b.adjust(1)
    await callback.message.edit_text(
        "📦 <b>Список товаров</b>\n\nВыберите товар для управления:",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:prod:"))
async def admin_product_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    prod_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        p = await session.get(
            Product, prod_id, options=[selectinload(Product.category)]
        )
    if not p:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="✏️ Название", callback_data=f"admin:editname:{p.id}")
    b.button(text="📝 Описание/замеры", callback_data=f"admin:editdesc:{p.id}")
    b.button(text="💰 Изменить цену", callback_data=f"admin:editprice:{p.id}")
    b.button(text="🚚 Изменить доставку", callback_data=f"admin:editdel:{p.id}")
    b.button(text="📸 Добавить фото", callback_data=f"admin:addphoto:{p.id}")
    b.button(text="🗂 Сменить категорию", callback_data=f"admin:editcat:{p.id}")
    status_txt = "👁 Скрыть из каталога" if p.is_active else "👁 Показать в каталоге"
    b.button(text=status_txt, callback_data=f"admin:toggle:{p.id}")
    b.button(text="🗑 Удалить товар", callback_data=f"admin:proddel:{p.id}")
    b.button(text="⬅️ К списку", callback_data="admin:products")
    b.adjust(2, 2, 2, 1, 1, 1)

    photos_count = len(p.photos)
    text = (
        f"🏷 <b>{p.name}</b>\n\n"
        f"💰 Цена: {int(p.price)} {settings.CURRENCY}\n"
        f"🚚 Доставка: {p.delivery_price}\n"
        f"🗂 Категория: {p.category.name if p.category else '—'}\n"
        f"🖼 Фото: {photos_count} шт.\n"
        f"⏱ Срок: {settings.delivery_range}\n"
        f"Статус: {'✅ в каталоге' if p.is_active else '🚫 скрыт'}\n\n"
        f"📝 <b>Описание/замеры:</b>\n{p.size_chart or '—'}"
    )
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:proddel:"))
async def admin_product_del(callback: CallbackQuery) -> None:
    prod_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        await session.execute(delete(Product).where(Product.id == prod_id))
        await session.commit()
    await callback.answer("Товар удалён.")
    await admin_products(callback, None)


@router.callback_query(F.data.startswith("admin:editprice:"))
async def admin_edit_price(callback: CallbackQuery, state: FSMContext) -> None:
    prod_id = int(callback.data.split(":")[2])
    await state.update_data(edit_prod_id=prod_id)
    await state.set_state(EditProduct.waiting_new_price)
    await callback.message.edit_text(
        "✏️ Введите <b>новую цену</b> товара числом:",
    )
    await callback.answer()


@router.message(EditProduct.waiting_new_price, F.text)
async def admin_save_price(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(" ", "")
    if not raw.isdigit():
        await message.answer("Введите цену числом.")
        return
    data = await state.get_data()
    async with session_maker() as session:
        p = await session.get(Product, data["edit_prod_id"])
        p.price = float(raw)
        await session.commit()
    await state.clear()
    await message.answer(f"✅ Цена обновлена: {int(float(raw))} {settings.CURRENCY}.",
                         reply_markup=admin_main_kb())


@router.callback_query(F.data.startswith("admin:editdel:"))
async def admin_edit_del(callback: CallbackQuery, state: FSMContext) -> None:
    prod_id = int(callback.data.split(":")[2])
    await state.update_data(edit_prod_id=prod_id)
    await state.set_state(EditProduct.waiting_new_delivery)
    await callback.message.edit_text(
        "🚚 Введите <b>новую стоимость доставки</b> (числом или «Бесплатно»):",
    )
    await callback.answer()


@router.message(EditProduct.waiting_new_delivery, F.text)
async def admin_save_del(message: Message, state: FSMContext) -> None:
    val = message.text.strip()
    data = await state.get_data()
    async with session_maker() as session:
        p = await session.get(Product, data["edit_prod_id"])
        p.delivery_price = val
        await session.commit()
    await state.clear()
    await message.answer(f"✅ Доставка обновлена: {val}", reply_markup=admin_main_kb())


# ============ Редактирование: название / описание / фото / статус / категория ============
async def _resend_admin_product(message: Message, prod_id: int) -> None:
    """Повторно показать карточку товара с актуальными данными."""
    async with session_maker() as session:
        p = await session.get(Product, prod_id, options=[selectinload(Product.category)])
    if not p:
        await message.answer("Товар не найден.", reply_markup=admin_main_kb())
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="✏️ Название", callback_data=f"admin:editname:{p.id}")
    b.button(text="📝 Описание/замеры", callback_data=f"admin:editdesc:{p.id}")
    b.button(text="💰 Изменить цену", callback_data=f"admin:editprice:{p.id}")
    b.button(text="🚚 Изменить доставку", callback_data=f"admin:editdel:{p.id}")
    b.button(text="📸 Добавить фото", callback_data=f"admin:addphoto:{p.id}")
    b.button(text="🗂 Сменить категорию", callback_data=f"admin:editcat:{p.id}")
    status_txt = "👁 Скрыть из каталога" if p.is_active else "👁 Показать в каталоге"
    b.button(text=status_txt, callback_data=f"admin:toggle:{p.id}")
    b.button(text="🗑 Удалить товар", callback_data=f"admin:proddel:{p.id}")
    b.button(text="⬅️ К списку", callback_data="admin:products")
    b.adjust(2, 2, 2, 1, 1, 1)

    text = (
        f"🏷 <b>{p.name}</b>\n\n"
        f"💰 Цена: {int(p.price)} {settings.CURRENCY}\n"
        f"🚚 Доставка: {p.delivery_price}\n"
        f"🗂 Категория: {p.category.name if p.category else '—'}\n"
        f"🖼 Фото: {len(p.photos)} шт.\n"
        f"Статус: {'✅ в каталоге' if p.is_active else '🚫 скрыт'}\n\n"
        f"📝 <b>Описание/замеры:</b>\n{p.size_chart or '—'}"
    )
    await message.answer(text, reply_markup=b.as_markup())


def _photos_done_admin_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="✅ Готово", callback_data="admin:photodone")
    return b.as_markup()


# --- Название ---
@router.callback_query(F.data.startswith("admin:editname:"))
async def admin_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_prod_id=int(callback.data.split(":")[2]))
    await state.set_state(EditProduct.waiting_new_name)
    await callback.message.edit_text(
        "✏️ Введите <b>новое название</b> товара:",
        reply_markup=_cancel_admin_kb(),
    )
    await callback.answer()


@router.message(EditProduct.waiting_new_name, F.text)
async def admin_save_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Слишком короткое название.")
        return
    data = await state.get_data()
    async with session_maker() as session:
        p = await session.get(Product, data["edit_prod_id"])
        p.name = name
        await session.commit()
    await state.clear()
    await message.answer(f"✅ Название обновлено: <b>{name}</b>")
    await _resend_admin_product(message, data["edit_prod_id"])


# --- Описание / замеры ---
@router.callback_query(F.data.startswith("admin:editdesc:"))
async def admin_edit_desc(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_prod_id=int(callback.data.split(":")[2]))
    await state.set_state(EditProduct.waiting_new_desc)
    await callback.message.edit_text(
        "📝 Пришлите <b>новое описание и замеры</b> товара "
        "одним сообщением (можно скопировать шаблон):\n\n" + SIZE_TEMPLATE,
        reply_markup=_cancel_admin_kb(),
    )
    await callback.answer()


@router.message(EditProduct.waiting_new_desc, F.text)
async def admin_save_desc(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    if len(desc) < 3:
        await message.answer("Описание слишком короткое.")
        return
    data = await state.get_data()
    async with session_maker() as session:
        p = await session.get(Product, data["edit_prod_id"])
        p.size_chart = desc
        await session.commit()
    await state.clear()
    await message.answer("✅ Описание/замеры обновлены.")
    await _resend_admin_product(message, data["edit_prod_id"])

# --- Добавить фото к существующему товару ---
@router.callback_query(F.data.startswith("admin:addphoto:"))
async def admin_add_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_prod_id=int(callback.data.split(":")[2]))
    await state.set_state(EditProduct.waiting_photos)
    await callback.message.edit_text(
        "📸 Отправьте <b>фото</b> товара (можно несколько, по одному).\n"
        "Они будут <b>добавлены</b> к уже имеющимся.\n\n"
        "Когда закончите — нажмите «Готово».",
        reply_markup=_photos_done_admin_kb(),
    )
    await callback.answer()


@router.message(EditProduct.waiting_photos, F.photo)
async def admin_add_photo_receive(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    file_id = message.photo[-1].file_id
    async with session_maker() as session:
        p = await session.get(Product, data["edit_prod_id"])
        photos = p.photos + [file_id]
        p.photos = photos
        await session.commit()
        count = len(photos)
    await message.answer(
        f"📸 Фото добавлено (всего: {count}). Отправьте ещё или нажмите «Готово».",
        reply_markup=_photos_done_admin_kb(),
    )


@router.callback_query(EditProduct.waiting_photos, F.data == "admin:photodone")
async def admin_add_photo_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer("Фото сохранены.")
    await callback.message.edit_text("✅ Фото к товару добавлены.")
    await _resend_admin_product(callback.message, data["edit_prod_id"])


# --- Скрыть / показать в каталоге ---
@router.callback_query(F.data.startswith("admin:toggle:"))
async def admin_toggle_product(callback: CallbackQuery) -> None:
    prod_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        p = await session.get(Product, prod_id)
        if p:
            p.is_active = not p.is_active
            await session.commit()
    await callback.answer("Статус товара изменён.")
    await admin_product_card(callback, None)


# --- Сменить категорию ---
@router.callback_query(F.data.startswith("admin:editcat:"))
async def admin_edit_cat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_prod_id=int(callback.data.split(":")[2]))
    async with session_maker() as session:
        cats = list(
            (await session.execute(select(Category).order_by(Category.id))).scalars().all()
        )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    for c in cats:
        b.button(text=c.name, callback_data=f"admin:setcat:{c.id}")
    b.button(text="❌ Отмена", callback_data="admin:menu")
    b.adjust(1)
    await state.set_state(EditProduct.waiting_new_category)
    await callback.message.edit_text(
        "🗂 Выберите <b>новую категорию</b> товара:", reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(EditProduct.waiting_new_category, F.data.startswith("admin:setcat:"))
async def admin_save_cat(callback: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    async with session_maker() as session:
        p = await session.get(Product, data["edit_prod_id"])
        if p:
            p.category_id = cat_id
            await session.commit()
    await state.clear()
    await callback.answer("Категория изменена.")
    await callback.message.edit_text("✅ Категория товара обновлена.")
    await _resend_admin_product(callback.message, data["edit_prod_id"])



# ============================================================
#  ЗАКАЗЫ
# ============================================================
@router.callback_query(F.data == "admin:orders")
async def admin_orders(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        orders = list(
            (
                await session.execute(
                    select(Order)
                    .options(selectinload(Order.items))
                    .order_by(Order.id.desc())
                )
            ).unique().scalars().all()
        )
    if not orders:
        await callback.message.edit_text(
            "📥 Заказов пока нет.",
            reply_markup=admin_main_kb(),
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    for o in orders:
        status_emoji = {"new": "🆕", "confirmed": "✅", "done": "✔️"}.get(o.status, "❓")
        b.button(text=f"{status_emoji} №{o.id} — {o.full_name[:20]}",
                 callback_data=f"admin:order:{o.id}")
    b.button(text="⬅️ Назад", callback_data="admin:menu")
    b.adjust(1)
    await callback.message.edit_text(
        "📥 <b>Входящие заказы</b>\n\nВыберите заказ:",
        reply_markup=b.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:order:"))
async def admin_order_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    order_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        o = await session.get(Order, order_id, options=[selectinload(Order.items)])
    if not o:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    items_txt = "\n".join(
        f"• {it.product_name} — размер {it.size} — {int(it.price)}{settings.CURRENCY} "
        f"(доставка: {it.delivery_price})"
        for it in o.items
    )
    text = (
        f"🧾 <b>Заказ №{o.id}</b> ({o.status})\n\n"
        f"👤 {o.full_name} (@{o.username})\n"
        f"🆔 {o.user_id}\n"
        f"📞 {o.phone}\n"
        f"📍 {o.address}\n\n"
        f"🛍 <b>Товары:</b>\n{items_txt}\n\n"
        f"💰 Итого: {int(o.total)} {settings.CURRENCY}\n"
        f"⏱ Срок: {settings.delivery_range}"
    )
    b = InlineKeyboardBuilder()
    if o.status == "new":
        b.button(text="✅ Подтвердить заказ", callback_data=f"admin:orderconfirm:{o.id}")
    b.button(text="⬅️ К заказам", callback_data="admin:orders")
    b.adjust(1)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:orderconfirm:"))
async def admin_order_confirm(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        o = await session.get(Order, order_id)
        if o:
            o.status = "confirmed"
            await session.commit()
    await callback.answer("Заказ подтверждён ✅")
    # Уведомляем клиента
    try:
        await callback.bot.send_message(
            o.user_id,
            f"✅ Ваш заказ №{order_id} подтверждён!\n"
            f"⏱ Срок доставки: {settings.delivery_range}.",
        )
    except Exception:
        pass
    await admin_order_card(callback, None)


# ============================================================
#  НАСТРОЙКИ ДОСТАВКИ (по умолчанию) — управление кнопками
# ============================================================
@router.callback_query(F.data == "admin:delivery")
async def admin_delivery(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DeliverySettings.waiting_min_days)
    await callback.message.edit_text(
        "🚚 <b>Настройки доставки</b>\n\n"
        f"Текущий срок для покупателей: <b>{settings.delivery_range}</b>\n\n"
        "<b>Шаг 1 из 2.</b> Введите <b>минимальный</b> срок доставки в днях\n"
        f"(сейчас: {settings.DELIVERY_MIN_DAYS}). Например: <code>18</code>",
        reply_markup=_cancel_admin_kb(),
    )
    await callback.answer()


@router.message(DeliverySettings.waiting_min_days, F.text)
async def admin_delivery_min(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 365):
        await message.answer("Введите целое число дней (1–365).")
        return
    await state.update_data(min_days=int(raw))
    await state.set_state(DeliverySettings.waiting_max_days)
    await message.answer(
        "<b>Шаг 2 из 2.</b> Теперь введите <b>максимальный</b> срок в днях "
        f"(сейчас: {settings.DELIVERY_MAX_DAYS}). Например: <code>25</code>",
        reply_markup=_cancel_admin_kb(),
    )


@router.message(DeliverySettings.waiting_max_days, F.text)
async def admin_delivery_max(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 365):
        await message.answer("Введите целое число дней (1–365).")
        return
    data = await state.get_data()
    min_days, max_days = data["min_days"], int(raw)
    if max_days < min_days:
        await message.answer("Максимум не может быть меньше минимума. Введите снова.")
        return

    # Сохраняем в БД и обновляем «живые» настройки бота
    from database.settings_store import set_setting

    await set_setting("delivery_min_days", min_days)
    await set_setting("delivery_max_days", max_days)
    settings.DELIVERY_MIN_DAYS = min_days
    settings.DELIVERY_MAX_DAYS = max_days

    await state.clear()
    await message.answer(
        f"✅ Срок доставки обновлён: <b>{settings.delivery_range}</b>\n\n"
        "Теперь это значение показывается всем покупателям.",
        reply_markup=admin_main_kb(),
    )


def _cancel_admin_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data="admin:menu")
    return b.as_markup()




# ============================================================
#  СТАТИСТИКА
# ============================================================
@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        orders_count = await session.scalar(select(func.count(Order.id))) or 0
        revenue = await session.scalar(select(func.sum(Order.total))) or 0.0
        new_orders = await session.scalar(
            select(func.count(Order.id)).where(Order.status == "new")
        ) or 0
        users_count = await session.scalar(select(func.count(User.id))) or 0
        products_count = await session.scalar(
            select(func.count(Product.id)).where(Product.is_active == True)  # noqa: E712
        ) or 0
        top = list(
            (
                await session.execute(
                    select(OrderItem.product_name, func.count(OrderItem.id).label("cnt"))
                    .group_by(OrderItem.product_name)
                    .order_by(func.count(OrderItem.id).desc())
                    .limit(5)
                )
            ).all()
        )

    top_txt = "\n".join(f"  {i}. {name} — {cnt} шт." for i, (name, cnt) in enumerate(top, 1))
    if not top_txt:
        top_txt = "  (пока нет продаж)"

    await callback.message.edit_text(
        "📊 <b>Статистика магазина</b>\n\n"
        f"🛍 Активных товаров: <b>{products_count}</b>\n"
        f"👥 Пользователей: <b>{users_count}</b>\n"
        f"🧾 Всего заказов: <b>{orders_count}</b>\n"
        f"🆕 Новых (не подтверждённых): <b>{new_orders}</b>\n"
        f"💰 Выручка: <b>{int(revenue)} {settings.CURRENCY}</b>\n\n"
        f"🏆 <b>Топ товаров:</b>\n{top_txt}",
        reply_markup=admin_main_kb(),
    )
    await callback.answer()


# ============================================================
#  РАССЫЛКА (Broadcast)
# ============================================================
@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Broadcast.waiting_content)
    await callback.message.edit_text(
        "📢 <b>Рассылка всем клиентам</b>\n\n"
        "Отправьте сообщение (текст или фото с подписью) — "
        "бот разошлёт его всем, кто нажимал /start.\n\n"
        "⚠️ Рассылка уйдёт сразу. Чтобы отменить — нажмите «Отмена».",
        reply_markup=_cancel_admin_kb(),
    )
    await callback.answer()


@router.message(Broadcast.waiting_content)
async def admin_broadcast_send(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        user_ids = list(
            (await session.execute(select(User.user_id))).scalars().all()
        )
    await message.answer(f"⏳ Начинаю рассылку по <b>{len(user_ids)}</b> пользователям...")

    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"✉️ Доставлено: <b>{sent}</b>\n"
        f"🚫 Не доставлено (заблокировали бота): <b>{failed}</b>",
        reply_markup=admin_main_kb(),
    )

# ============================================================
#  ПРОМОКОДЫ
# ============================================================
@router.callback_query(F.data == "admin:promos")
async def admin_promos(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _render_promos(callback)


async def _render_promos(callback: CallbackQuery) -> None:
    async with session_maker() as session:
        promos = list(
            (await session.execute(select(Promo).order_by(Promo.id.desc()))).scalars().all()
        )
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    for p in promos:
        status = "✅" if p.is_active else "🚫"
        b.button(text=f"{status} {p.code} — {p.discount_percent}%",
                 callback_data=f"admin:promotoggle:{p.id}")
    b.button(text="➕ Создать промокод", callback_data="admin:promoadd")
    b.button(text="⬅️ Назад", callback_data="admin:menu")
    b.adjust(1)
    text = "🎟 <b>Промокоды</b>\n\n"
    text += (
        "\n".join(
            f"• <code>{p.code}</code> — {p.discount_percent}% "
            f"({'активен' if p.is_active else 'выключен'}), использован: {p.used_count}"
            for p in promos
        )
        if promos
        else "Пока нет промокодов. Создайте первый!"
    )
    await callback.message.edit_text(text, reply_markup=b.as_markup())


@router.callback_query(F.data == "admin:promoadd")
async def admin_promo_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoAdmin.waiting_code)
    await callback.message.edit_text(
        "🎟 Введите <b>код промокода</b> (латиницей, например: <code>SALE10</code>):",
        reply_markup=_cancel_admin_kb(),
    )
    await callback.answer()


@router.message(PromoAdmin.waiting_code, F.text)
async def admin_promo_code(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper().replace(" ", "")
    if len(code) < 3:
        await message.answer("Код слишком короткий. Минимум 3 символа.")
        return
    await state.update_data(promo_code=code)
    await state.set_state(PromoAdmin.waiting_percent)
    await message.answer(
        "Введите <b>размер скидки в процентах</b> (число от 1 до 90). Например: <code>10</code>",
        reply_markup=_cancel_admin_kb(),
    )


@router.message(PromoAdmin.waiting_percent, F.text)
async def admin_promo_percent(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 90):
        await message.answer("Введите целое число от 1 до 90.")
        return
    data = await state.get_data()
    async with session_maker() as session:
        exists = await session.scalar(select(Promo).where(Promo.code == data["promo_code"]))
        if exists:
            await state.clear()
            await message.answer("Такой код уже есть. Попробуйте другой.")
            await message.answer(admin_menu_text(), reply_markup=admin_main_kb())
            return
        session.add(Promo(code=data["promo_code"], discount_percent=int(raw)))
        await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Промокод <code>{data['promo_code']}</code> на {raw}% создан!",
        reply_markup=admin_main_kb(),
    )


@router.callback_query(F.data.startswith("admin:promotoggle:"))
async def admin_promo_toggle(callback: CallbackQuery) -> None:
    promo_id = int(callback.data.split(":")[2])
    async with session_maker() as session:
        p = await session.get(Promo, promo_id)
        if p:
            p.is_active = not p.is_active
            await session.commit()
    await callback.answer("Статус промокода изменён.")
    await _render_promos(callback)


# ============================================================
#  ОТЗЫВЫ
# ============================================================
@router.callback_query(F.data == "admin:reviews")
async def admin_reviews(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    async with session_maker() as session:
        reviews = list(
            (
                await session.execute(
                    select(Review).order_by(Review.id.desc()).limit(15)
                )
            ).scalars().all()
        )
        avg = await session.scalar(select(func.avg(Review.rating)))
        count = await session.scalar(select(func.count(Review.id))) or 0

    avg_txt = f"{avg:.1f} ⭐" if avg else "нет оценок"
    if reviews:
        lines = [f"⭐ <b>Отзывы</b> (средняя: {avg_txt}, всего: {count})\n"]
        for r in reviews:
            lines.append(
                f"{'⭐' * r.rating} — заказ №{r.order_id}\n{r.text or '(без текста)'}\n"
            )
        text = "\n".join(lines)
    else:
        text = "⭐ Отзывов пока нет."
    await callback.message.edit_text(text, reply_markup=admin_main_kb())
    await callback.answer()

