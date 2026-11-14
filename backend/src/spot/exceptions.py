from src.exceptions import ConflictError, EntityNotFoundError


class SpotNotFoundError(EntityNotFoundError):
    entity = "Spot"


class SpotAlreadyExistsError(ConflictError):
    detail = "A spot with this name already exists in the city"
