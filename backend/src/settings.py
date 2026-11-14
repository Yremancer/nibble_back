from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from src.auth.constants import (
    JWT_SECRET_MIN_LENGTH,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BACKEND_PORT: int

    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str
    ALLOWED_ORIGINS: str

    WEATHER_CACHE_TTL_MINUTES: int = 15

    TACKLE_UTM_PARAMS: str = "utm_source=klev&utm_medium=referral"

    JWT_SECRET_KEY: SecretStr = Field(min_length=JWT_SECRET_MIN_LENGTH)
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    AUTH_REFRESH_COOKIE_NAME: str = "refresh_token"
    AUTH_REFRESH_COOKIE_PATH: str = "/auth"
    AUTH_REFRESH_COOKIE_SECURE: bool = True
    AUTH_PASSWORD_MIN_LENGTH: int = 8

    S3_ENDPOINT_URL: str
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_BUCKET: str
    S3_REGION: str = "us-east-1"

    @property
    def ORIGINS(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
