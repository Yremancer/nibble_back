from src.exceptions import AppError, EntityNotFoundError


class PostNotFoundError(EntityNotFoundError):
    entity = "Post"


class InvalidCursorError(AppError):
    status_code = 422
    detail = "Invalid cursor"
