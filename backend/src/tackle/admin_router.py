from fastapi import APIRouter, status
from src.auth.deps import ModeratorDep
from src.tackle.admin_schemas import (
    CategoryAdminOut,
    CategoryCreate,
    CategoryUpdate,
    LinkAdminOut,
    LinkCreate,
    LinkUpdate,
)
from src.tackle.deps import TackleAdminServiceDep

router = APIRouter(prefix="/admin/tackle", tags=["admin"])


@router.get("/categories", response_model=list[CategoryAdminOut])
async def list_categories(_staff: ModeratorDep, service: TackleAdminServiceDep):
    return await service.list_categories()


@router.post(
    "/categories", response_model=CategoryAdminOut, status_code=status.HTTP_201_CREATED
)
async def create_category(
    data: CategoryCreate, _staff: ModeratorDep, service: TackleAdminServiceDep
):
    return await service.create_category(data)


@router.patch("/categories/{category_id}", response_model=CategoryAdminOut)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    _staff: ModeratorDep,
    service: TackleAdminServiceDep,
):
    return await service.update_category(category_id, data)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int, _staff: ModeratorDep, service: TackleAdminServiceDep
) -> None:
    await service.delete_category(category_id)


@router.get("/links", response_model=list[LinkAdminOut])
async def list_links(
    _staff: ModeratorDep,
    service: TackleAdminServiceDep,
    city_id: int | None = None,
    category_id: int | None = None,
    is_active: bool | None = None,
    q: str | None = None,
):
    return await service.list_links(city_id, category_id, is_active, q)


@router.post("/links", response_model=LinkAdminOut, status_code=status.HTTP_201_CREATED)
async def create_link(data: LinkCreate, _staff: ModeratorDep, service: TackleAdminServiceDep):
    return await service.create_link(data)


@router.get("/links/{link_id}", response_model=LinkAdminOut)
async def get_link(link_id: int, _staff: ModeratorDep, service: TackleAdminServiceDep):
    return await service.get_link(link_id)


@router.patch("/links/{link_id}", response_model=LinkAdminOut)
async def update_link(
    link_id: int, data: LinkUpdate, _staff: ModeratorDep, service: TackleAdminServiceDep
):
    return await service.update_link(link_id, data)


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    link_id: int, _staff: ModeratorDep, service: TackleAdminServiceDep
) -> None:
    await service.delete_link(link_id)
