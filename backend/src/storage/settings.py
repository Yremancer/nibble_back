from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """S3/MinIO настройки. Все поля опциональны: до подключения реального
    S3 (готовится отдельно) агрегатор должен запускаться и выполнять все
    независимые этапы, кроме собственно загрузки медиа."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    S3_ENDPOINT_URL: str | None = None
    S3_REGION: str | None = None
    S3_BUCKET: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_ADDRESSING_STYLE: str = "path"
    S3_PUBLIC_BASE_URL: str | None = None
    """Публичный базовый адрес/CDN. Если не задан, выдаются подписанные URL."""
    S3_SIGNED_URL_TTL_S: int = 3600
    S3_MAX_UPLOAD_CONCURRENCY: int = 4
    S3_MAX_FILE_SIZE_BYTES: int = 300 * 1024 * 1024

    @property
    def is_configured(self) -> bool:
        return bool(
            self.S3_ENDPOINT_URL and self.S3_BUCKET and self.S3_ACCESS_KEY
            and self.S3_SECRET_KEY
        )


storage_settings = StorageSettings()
