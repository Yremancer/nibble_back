class StorageError(Exception):
    """Базовая ошибка хранилища."""


class StorageNotConfiguredError(StorageError):
    """S3 ещё не подключён (настройки не заданы)."""


class DownloadError(StorageError):
    """Не удалось скачать вложение: сеть, лимит размера, недоступный адрес."""


class UnsafeUrlError(DownloadError):
    """URL указывает на локальный/служебный адрес (защита от SSRF)."""


class FileTooLargeError(DownloadError):
    pass


class UploadError(StorageError):
    pass
