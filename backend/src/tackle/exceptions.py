from src.exceptions import ConflictError, EntityNotFoundError


class TackleCategoryNotFoundError(EntityNotFoundError):
    entity = "Tackle category"


class TackleLinkNotFoundError(EntityNotFoundError):
    entity = "Tackle link"


class TackleCategoryAlreadyExistsError(ConflictError):
    detail = "A tackle category with this name already exists"


class TackleCategoryInUseError(ConflictError):
    detail = "Tackle category has links"
