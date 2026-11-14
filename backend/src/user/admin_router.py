from typing import Annotated

from fastapi import APIRouter, Query, status
from src.auth.deps import AdminDep
from src.user.admin_schemas import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserPage,
    AdminUserQuery,
    RoleUpdate,
)
from src.user.deps import AdminUserServiceDep

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get(
    "",
    response_model=AdminUserPage,
    description="Пользователи с постраничной подгрузкой (cursor = id последнего). Фильтры: role, q (email или имя).",
)
async def list_users(
    query: Annotated[AdminUserQuery, Query()],
    _admin: AdminDep,
    service: AdminUserServiceDep,
) -> AdminUserPage:
    return await service.list_users(query)


@router.post(
    "",
    response_model=AdminUserOut,
    status_code=status.HTTP_201_CREATED,
    description="Создать пользователя сразу с нужной ролью (user, moderator, admin).",
)
async def create_user(
    data: AdminUserCreate, _admin: AdminDep, service: AdminUserServiceDep
) -> AdminUserOut:
    return await service.create(data)


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: int, _admin: AdminDep, service: AdminUserServiceDep
) -> AdminUserOut:
    return await service.get_user(user_id)


@router.patch(
    "/{user_id}/role",
    response_model=AdminUserOut,
    description="Назначить роль. Свою роль менять нельзя. Действует сразу, перелогиниваться не нужно.",
)
async def set_role(
    user_id: int,
    data: RoleUpdate,
    admin: AdminDep,
    service: AdminUserServiceDep,
) -> AdminUserOut:
    return await service.set_role(user_id, data.role, admin)
