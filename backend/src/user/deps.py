from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.post.repository import PostRepository
from src.storage.deps import ImageServiceDep
from src.user.admin_service import AdminUserService
from src.user.profile_service import ProfileService
from src.user.repository import UserRepository
from src.user.service import UserService


def get_user_service(session: SessionDep, images: ImageServiceDep) -> UserService:
    return UserService(UserRepository(session), images)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_profile_service(session: SessionDep, images: ImageServiceDep) -> ProfileService:
    return ProfileService(UserRepository(session), PostRepository(session), images)


ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]


def get_admin_user_service(session: SessionDep, images: ImageServiceDep) -> AdminUserService:
    repo = UserRepository(session)
    return AdminUserService(repo, UserService(repo, images), images)


AdminUserServiceDep = Annotated[AdminUserService, Depends(get_admin_user_service)]
