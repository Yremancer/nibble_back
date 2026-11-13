class LlmError(Exception):
    """Базовая ошибка клиента LLM."""


class LlmNotConfiguredError(LlmError):
    pass


class LlmRequestError(LlmError):
    """Сетевая ошибка, таймаут или превышен лимит попыток."""


class LlmInvalidResponseError(LlmError):
    """Ответ не прошёл валидацию Pydantic-схемой."""
