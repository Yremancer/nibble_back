from src.exceptions import ConflictError, EntityNotFoundError


class SpeciesNotFoundError(EntityNotFoundError):
    entity = "Species"


class SpeciesAlreadyExistsError(ConflictError):
    detail = "A species with this name already exists"


class SpeciesInUseError(ConflictError):
    detail = "Species is used in posts"


class MethodNotFoundError(EntityNotFoundError):
    entity = "Fishing method"


class MethodAlreadyExistsError(ConflictError):
    detail = "A fishing method with this name already exists"


class MethodInUseError(ConflictError):
    detail = "Fishing method is used in posts"
