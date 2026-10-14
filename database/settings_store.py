from sqlalchemy import select

from database.db import session_maker
from database.models import Setting


async def get_setting(key: str, default: str = "") -> str:
    """Читает значение настройки из БД (или default)."""
    async with session_maker() as session:
        value = await session.scalar(select(Setting.value).where(Setting.key == key))
    return value if value is not None else default


async def set_setting(key: str, value) -> None:
    """Сохраняет/обновляет настройку в БД."""
    async with session_maker() as session:
        row = await session.scalar(select(Setting).where(Setting.key == key))
        if row:
            row.value = str(value)
        else:
            session.add(Setting(key=key, value=str(value)))
        await session.commit()
