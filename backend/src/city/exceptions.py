from src.exceptions import EntityNotFoundError


class CityNotFoundError(EntityNotFoundError):
    entity = "City"
