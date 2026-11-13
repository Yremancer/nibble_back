from src.exceptions import AppError, EntityNotFoundError
from src.spot.exceptions import SpotNotFoundError

__all__ = ["CityNotFoundError", "SpotNotFoundError", "WeatherUnavailableError"]


class CityNotFoundError(EntityNotFoundError):
    entity = "City"


class WeatherUnavailableError(AppError):
    status_code = 503
    detail = "Weather provider is unavailable"
