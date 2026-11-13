from src.city.exceptions import CityNotFoundError
from src.exceptions import AppError
from src.spot.exceptions import SpotNotFoundError

__all__ = ["CityNotFoundError", "SpotNotFoundError", "WeatherUnavailableError"]


class WeatherUnavailableError(AppError):
    status_code = 503
    detail = "Weather provider is unavailable"
