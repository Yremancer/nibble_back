from fastapi import APIRouter, status
from src.auth.deps import ModeratorDep
from src.spot.admin_schemas import SpotAdminItem, SpotAdminOut, SpotCreate, SpotUpdate
from src.spot.deps import SpotAdminServiceDep

router = APIRouter(prefix="/admin/spots", tags=["admin"])


@router.get("", response_model=list[SpotAdminItem])
async def list_spots(
    _staff: ModeratorDep,
    service: SpotAdminServiceDep,
    city_id: int | None = None,
    is_active: bool | None = None,
    q: str | None = None,
):
    return await service.list_spots(city_id, is_active, q)


@router.post("", response_model=SpotAdminOut, status_code=status.HTTP_201_CREATED)
async def create_spot(data: SpotCreate, staff: ModeratorDep, service: SpotAdminServiceDep):
    return await service.create(data, staff)


@router.get("/{spot_id}", response_model=SpotAdminOut)
async def get_spot(spot_id: int, _staff: ModeratorDep, service: SpotAdminServiceDep):
    return await service.get_spot(spot_id)


@router.patch("/{spot_id}", response_model=SpotAdminOut)
async def update_spot(
    spot_id: int, data: SpotUpdate, staff: ModeratorDep, service: SpotAdminServiceDep
):
    return await service.update(spot_id, data, staff)


@router.delete("/{spot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spot(spot_id: int, _staff: ModeratorDep, service: SpotAdminServiceDep) -> None:
    await service.deactivate(spot_id)
