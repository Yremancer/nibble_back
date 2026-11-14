from typing import Annotated

from fastapi import APIRouter, Query, status
from src.auth.deps import AdminDep, CurrentUserDep, OptionalUserDep
from src.user.deps import ProfileServiceDep, UserServiceDep
from src.user.schemas import (
    FollowListQuery,
    ProfileOut,
    UserPage,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
async def list_users(_admin: AdminDep, service: UserServiceDep):
    return await service.list_users()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, actor: CurrentUserDep, service: UserServiceDep):
    return await service.get_user(user_id, actor)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int, data: UserUpdate, actor: CurrentUserDep, service: UserServiceDep
):
    return await service.update(user_id, data, actor)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, actor: CurrentUserDep, service: UserServiceDep) -> None:
    await service.delete(user_id, actor)


@router.get("/{user_id}/profile", response_model=ProfileOut)
async def get_profile(
    user_id: int, viewer: OptionalUserDep, service: ProfileServiceDep
) -> ProfileOut:
    return await service.get_profile(user_id, viewer)


@router.put("/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def follow(user_id: int, actor: CurrentUserDep, service: ProfileServiceDep) -> None:
    await service.follow(user_id, actor)


@router.delete("/{user_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow(user_id: int, actor: CurrentUserDep, service: ProfileServiceDep) -> None:
    await service.unfollow(user_id, actor)


@router.get("/{user_id}/followers", response_model=UserPage)
async def get_followers(
    user_id: int,
    query: Annotated[FollowListQuery, Query()],
    viewer: OptionalUserDep,
    service: ProfileServiceDep,
) -> UserPage:
    return await service.followers(user_id, viewer, query.cursor, query.limit)


@router.get("/{user_id}/following", response_model=UserPage)
async def get_following(
    user_id: int,
    query: Annotated[FollowListQuery, Query()],
    viewer: OptionalUserDep,
    service: ProfileServiceDep,
) -> UserPage:
    return await service.following(user_id, viewer, query.cursor, query.limit)
