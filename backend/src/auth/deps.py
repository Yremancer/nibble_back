from typing import Annotated

from fastapi import Cookie, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.auth.exceptions import AuthenticationError
from src.auth.repository import AuthSessionRepository
from src.auth.service import AuthService
from src.database.deps import SessionDep
from src.exceptions import ForbiddenError
from src.settings import settings
from src.user.deps import UserServiceDep
from src.user.models import User, UserRole

BEARER_AUTH = HTTPBearer(auto_error=False)
RefreshCookie = Annotated[str | None, Cookie(alias=settings.AUTH_REFRESH_COOKIE_NAME)]


def get_auth_service(users: UserServiceDep, session: SessionDep) -> AuthService:
    return AuthService(users, AuthSessionRepository(session))


def check_auth_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in (
        str(request.base_url).rstrip("/"),
        *settings.ORIGINS,
    ):
        raise ForbiddenError("Untrusted request origin")


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER_AUTH)],
    service: AuthServiceDep,
) -> User | None:
    if credentials is None:
        return None
    return await service.current_user(credentials.credentials)


OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: OptionalUserDep) -> User:
    if user is None:
        raise AuthenticationError
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    async def check_role(user: CurrentUserDep) -> User:
        if user.role not in roles:
            raise ForbiddenError
        return user

    return check_role


ModeratorDep = Annotated[
    User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))
]
AdminDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
