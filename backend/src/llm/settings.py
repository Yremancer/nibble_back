from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmSettings(BaseSettings):

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TIMEOUT_S: float = 30.0
    DEEPSEEK_MAX_CONCURRENCY: int = 3
    DEEPSEEK_MAX_RETRIES: int = 3
    DEEPSEEK_MAX_INPUT_CHARS: int = 8000
    DEEPSEEK_MAX_REQUESTS_PER_RUN: int | None = None

    PROMPT_VERSION: str = "v1"

    @property
    def is_configured(self) -> bool:
        return bool(self.DEEPSEEK_API_KEY)


llm_settings = LlmSettings()
