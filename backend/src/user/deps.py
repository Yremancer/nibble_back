from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.user.repository import UserRepository
from src.user.service import UserService


def get_user_service(session: SessionDep) -> UserService:
    return UserService(UserRepository(session))


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
