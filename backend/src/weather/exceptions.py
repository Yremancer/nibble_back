from src.exceptions import AppError, EntityNotFoundError


class CityNotFoundError(EntityNotFoundError):
    entity = "City"


class SpotNotFoundError(EntityNotFoundError):
    entity = "Spot"


class WeatherUnavailableError(AppError):
    status_code = 503
    detail = "Weather provider is unavailable"
