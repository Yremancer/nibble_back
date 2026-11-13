from fastapi import APIRouter, status
from src.auth.deps import AdminDep, CurrentUserDep
from src.user.deps import UserServiceDep
from src.user.schemas import UserResponse, UserUpdate

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
