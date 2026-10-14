from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки бота, загружаемые из .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    BOT_TOKEN: str = ""
    ADMIN_IDS: str = ""
    CURRENCY: str = "сом"

    # Контакт менеджера, который видит клиент (подставьте свой @username)
    MANAGER_USERNAME: str = "@your_manager"

    # Авто-подтверждение заказов: True — заказ подтверждается сразу,
    # клиент получает уведомление без участия менеджера.
    AUTO_CONFIRM_ORDERS: bool = True

    DELIVERY_MIN_DAYS: int = 18
    DELIVERY_MAX_DAYS: int = 25

    DB_NAME: str = "shop.db"

    @property
    def admin_ids(self) -> list[int]:
        """Список ID админов из строки '123,456'."""
        return [int(x) for x in self.ADMIN_IDS.replace(" ", "").split(",") if x]

    @property
    def delivery_range(self) -> str:
        """Строка срока доставки, которую видит клиент: '18-25 дней'."""
        return f"{self.DELIVERY_MIN_DAYS}-{self.DELIVERY_MAX_DAYS} дней"


settings = Settings()
