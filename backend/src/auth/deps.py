from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.auth.exceptions import AuthenticationError
from src.auth.repository import AuthRepository
from src.auth.service import AuthService
from src.database.deps import SessionDep
from src.exceptions import ForbiddenError
from src.models.user import User, UserRole

BEARER_AUTH = HTTPBearer(auto_error=False)


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(AuthRepository(session))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER_AUTH)],
    service: AuthServiceDep,
) -> User:
    if credentials is None:
        raise AuthenticationError
    return await service.current_user(credentials.credentials)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    async def check_role(user: CurrentUserDep) -> User:
        if user.role not in roles:
            raise ForbiddenError
        return user

    return check_role


ModeratorDep = Annotated[User, Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN))]
AdminDep = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
