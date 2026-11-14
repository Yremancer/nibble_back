from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.post.repository import PostRepository
from src.user.profile_service import ProfileService
from src.user.repository import UserRepository
from src.user.service import UserService


def get_user_service(session: SessionDep) -> UserService:
    return UserService(UserRepository(session))


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_profile_service(session: SessionDep) -> ProfileService:
    return ProfileService(UserRepository(session), PostRepository(session))


ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
