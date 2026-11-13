from src.exceptions import AppError


class AuthenticationError(AppError):
    status_code = 401
    detail = "Invalid credentials or token"
    headers = {"WWW-Authenticate": "Bearer"}
