from src.exceptions import AppError, EntityNotFoundError, ForbiddenError


class PostNotFoundError(EntityNotFoundError):
    entity = "Post"


class PostForbiddenError(ForbiddenError):
    detail = "You can modify only your own posts"


class InvalidPostError(AppError):
    status_code = 422
    detail = "Invalid post data"


class KlevSourceMissingError(AppError):
    status_code = 503
    detail = "Source 'klev' is not configured"


class InvalidCursorError(AppError):
    status_code = 422
    detail = "Invalid cursor"


class ImportedPostLikeError(ForbiddenError):
    detail = "Imported posts cannot be liked"


class CommentNotFoundError(EntityNotFoundError):
    entity = "Comment"


class CommentForbiddenError(ForbiddenError):
    detail = "You can delete only your own comments"
