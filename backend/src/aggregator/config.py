"""Конфигурация источников и лимитов агрегатора.

Подключение нового Telegram-канала — правка sources.json, без изменения
кода сборщика (см. ТЗ, раздел 2).
"""

import json
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SOURCES_PATH = Path(__file__).parent / "sources.json"


class TelegramSourceConfig(BaseModel):
    name: str
    channel: str
    """Username или -100... ID канала. Используется для первого resolve;
    далее источник привязывается к стабильному Telegram ID, не к username."""
    city_id: int | None = None
    is_active: bool = True


class NormalizationRule(BaseModel):
    """Регулярное выражение служебного хвоста конкретного источника,
    убираемого из текста перед классификацией/дедупликацией."""

    pattern: str
    flags: str = "IGNORECASE|DOTALL"


class SourcesConfig(BaseModel):
    telegram: list[TelegramSourceConfig] = []
    normalization: dict[str, list[NormalizationRule]] = {}
    """Ключ — channel (как в telegram[].channel), значение — список правил."""


def load_sources_config(path: Path | None = None) -> SourcesConfig:
    config_path = path or _DEFAULT_SOURCES_PATH
    if not config_path.exists():
        return SourcesConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return SourcesConfig.model_validate(data)


class AggregatorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    AGG_TIMEZONE: str = "Asia/Vladivostok"
    AGG_BACKFILL_DEPTH_DAYS: int = 365
    AGG_RECHECK_WINDOW_HOURS: int = 72
    """Окно повторной проверки недавних сообщений на редактирование."""
    AGG_BATCH_SIZE: int = 50
    AGG_RAW_RETENTION_DAYS: int = 180
    """Срок хранения тяжёлых сырых ответов/временных файлов. Не затрагивает
    данные, нужные работающим публикациям."""

    TELEGRAM_API_ID: int | None = None
    TELEGRAM_API_HASH: str | None = None
    TELEGRAM_PHONE: str | None = None
    TELEGRAM_SESSION_PATH: str = "/app/data/telegram.session"

    FARPOST_BASE_URL: str = "https://www.farpost.ru"
    FARPOST_CITY_PATH: str = "vladivostok/sport/fish/"
    FARPOST_REQUEST_DELAY_S: float = 1.5
    FARPOST_MAX_CONCURRENCY: int = 2

    FISHING_VL_BASE_URL: str = "https://fishing-vl.ru"

    @property
    def is_telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_API_ID and self.TELEGRAM_API_HASH)

    def prepare_telegram_session(self) -> str:
        path = Path(self.TELEGRAM_SESSION_PATH).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)


aggregator_settings = AggregatorSettings()
