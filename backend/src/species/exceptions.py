from src.exceptions import EntityNotFoundError


class SpeciesNotFoundError(EntityNotFoundError):
    entity = "Species"
