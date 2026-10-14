from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

# Асинхронный движок SQLite
engine = create_async_engine(f"sqlite+aiosqlite:///{settings.DB_NAME}", echo=False)

# Фабрика сессий
session_maker = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def create_tables() -> None:
    """Создаёт все таблицы в БД (вызывается при старте бота)."""
    from database.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
