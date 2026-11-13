from src.exceptions import EntityNotFoundError


class SpotNotFoundError(EntityNotFoundError):
    entity = "Spot"
