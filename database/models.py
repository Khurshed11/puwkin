import json
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ==================== Категории ====================
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    products: Mapped[list["Product"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )


# ==================== Товары ====================
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Цена товара в национальной валюте (число). 0 = не указано.
    price: Mapped[float] = mapped_column(Float, default=0.0)
    # Стоимость доставки текстом: "500", "Бесплатно" и т.п.
    delivery_price: Mapped[str] = mapped_column(String(100), default="Бесплатно")

    # Текстовая размерная сетка / замеры, заполняемая админом по шаблону
    size_chart: Mapped[str] = mapped_column(Text, default="")

    # file_id фотографий, храним как JSON-массив
    photo_ids: Mapped[str] = mapped_column(Text, default="[]")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped["Category"] = relationship(back_populates="products")

    @property
    def photos(self) -> list[str]:
        """Список file_id фотографий."""
        try:
            return json.loads(self.photo_ids)
        except (json.JSONDecodeError, TypeError):
            return []

    @photos.setter
    def photos(self, value: list[str]) -> None:
        self.photo_ids = json.dumps(value, ensure_ascii=False)


# ==================== Настройки магазина (по умолчанию) ====================
class Setting(Base):
    """Ключ-значение для настроек, которые может менять админ."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, default="")


# ==================== Корзина ====================
class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    size: Mapped[str] = mapped_column(String(50), default="—")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["Product"] = relationship()


# ==================== Заказы ====================
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str] = mapped_column(String(100), default="—")
    full_name: Mapped[str] = mapped_column(String(200), default="—")

    # Контакты и адрес, введённые при оформлении
    phone: Mapped[str] = mapped_column(String(100), default="—")
    address: Mapped[str] = mapped_column(Text, default="—")

    status: Mapped[str] = mapped_column(String(50), default="new")  # new/confirmed/done
    total: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[str] = mapped_column(String(50), default="—")
    price: Mapped[float] = mapped_column(Float, default=0.0)
    delivery_price: Mapped[str] = mapped_column(String(100), default="—")

    order: Mapped["Order"] = relationship(back_populates="items")


# ==================== Пользователи (для рассылки и статистики) ====================
class User(Base):
    """Все, кто нажал /start — база для рассылки и отчётов."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), default="—")
    full_name: Mapped[str] = mapped_column(String(200), default="—")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)  # заблокировал бота
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ==================== Промокоды ====================
class Promo(Base):
    """Скидочный промокод (процент скидки на товары)."""

    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    discount_percent: Mapped[int] = mapped_column(Integer, default=10)  # 1..99
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ==================== Отзывы ====================
class Review(Base):
    """Оценка и текст отзыва о заказе."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    order_id: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[int] = mapped_column(Integer, default=5)  # 1..5
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ==================== Избранное (Wishlist) ====================
class Favorite(Base):
    """Товары, сохранённые клиентом в «Избранное»."""

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["Product"] = relationship(lazy="selectin")
