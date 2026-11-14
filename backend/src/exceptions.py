class AppError(Exception):
    status_code = 500
    detail = "Internal error"
    headers: dict[str, str] | None = None

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    detail = "Not found"


class EntityNotFoundError(NotFoundError):
    entity = "Entity"

    def __init__(self, **criteria: object) -> None:
        conditions = ", ".join(f"{k}={v!r}" for k, v in criteria.items())
        super().__init__(f"{self.entity} not found ({conditions})")


class ConflictError(AppError):
    status_code = 409
    detail = "Conflict"


class ForbiddenError(AppError):
    status_code = 403
    detail = "Forbidden"


class InvalidCursorError(AppError):
    status_code = 422
    detail = "Invalid cursor"
