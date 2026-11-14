from src.exceptions import AppError, ConflictError, EntityNotFoundError


class UserNotFoundError(EntityNotFoundError):
    entity = "User"


class EmailAlreadyRegisteredError(ConflictError):
    detail = "Email is already registered"


class InvalidCityError(AppError):
    status_code = 422
    detail = "City does not exist"


class CannotFollowSelfError(AppError):
    status_code = 422
    detail = "You cannot follow yourself"
