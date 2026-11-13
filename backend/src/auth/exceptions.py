from src.exceptions import AppError, ConflictError


class AuthenticationError(AppError):
    status_code = 401
    detail = "Invalid credentials or token"
    headers = {"WWW-Authenticate": "Bearer"}


class EmailAlreadyRegisteredError(ConflictError):
    detail = "Email is already registered"


class InvalidCityError(AppError):
    status_code = 422
    detail = "City does not exist"
