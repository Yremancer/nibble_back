from src.exceptions import AppError


class StorageError(AppError):
    status_code = 502
    detail = "Storage error"


class StorageUnavailableError(StorageError):
    status_code = 503
    detail = "Storage is unavailable"


class FileNotFoundInStorageError(StorageError):
    status_code = 404
    detail = "File not found"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    detail = "Unsupported file type"


class FileTooLargeError(AppError):
    status_code = 413
    detail = "File is too large"
