from fastapi import APIRouter, status
from src.auth.deps import ModeratorDep
from src.species.admin_schemas import (
    MethodCreate,
    MethodUpdate,
    SpeciesAdminOut,
    SpeciesCreate,
    SpeciesUpdate,
)
from src.species.deps import SpeciesAdminServiceDep
from src.species.schemas import FishingMethodOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/species", response_model=list[SpeciesAdminOut])
async def list_species(
    _staff: ModeratorDep, service: SpeciesAdminServiceDep, q: str | None = None
):
    return await service.list_species(q)


@router.post("/species", response_model=SpeciesAdminOut, status_code=status.HTTP_201_CREATED)
async def create_species(
    data: SpeciesCreate, _staff: ModeratorDep, service: SpeciesAdminServiceDep
):
    return await service.create(data)


@router.get("/species/{species_id}", response_model=SpeciesAdminOut)
async def get_species(
    species_id: int, _staff: ModeratorDep, service: SpeciesAdminServiceDep
):
    return await service.get_species(species_id)


@router.patch("/species/{species_id}", response_model=SpeciesAdminOut)
async def update_species(
    species_id: int,
    data: SpeciesUpdate,
    _staff: ModeratorDep,
    service: SpeciesAdminServiceDep,
):
    return await service.update(species_id, data)


@router.delete("/species/{species_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_species(
    species_id: int, _staff: ModeratorDep, service: SpeciesAdminServiceDep
) -> None:
    await service.delete(species_id)


@router.post(
    "/fishing-methods",
    response_model=FishingMethodOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_method(
    data: MethodCreate, _staff: ModeratorDep, service: SpeciesAdminServiceDep
):
    return await service.create_method(data)


@router.patch("/fishing-methods/{method_id}", response_model=FishingMethodOut)
async def update_method(
    method_id: int,
    data: MethodUpdate,
    _staff: ModeratorDep,
    service: SpeciesAdminServiceDep,
):
    return await service.update_method(method_id, data)


@router.delete("/fishing-methods/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_method(
    method_id: int, _staff: ModeratorDep, service: SpeciesAdminServiceDep
) -> None:
    await service.delete_method(method_id)
