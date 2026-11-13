from src.exceptions import AppError


class DownloadError(AppError):
    status_code = 502
    detail = "Media download failed"


class UnsafeUrlError(DownloadError):
    detail = "Unsafe media URL"


class FarpostUnavailableError(AppError):
    status_code = 502
    detail = "Не удалось получить объявления Farpost"


class TelegramUnavailableError(AppError):
    status_code = 502
    detail = "Не удалось получить публикации Telegram"
