from typing import Annotated

from fastapi import APIRouter, Query
from src.species.deps import SpeciesServiceDep
from src.species.schemas import FishingMethodOut, Season, SpeciesOut, SpeciesShort

router = APIRouter(tags=["species"])


@router.get("/species", response_model=list[SpeciesShort])
async def list_species(
    service: SpeciesServiceDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    season: Season | None = None,
):
    return await service.list_species(q, season)


@router.get("/species/{species_id}", response_model=SpeciesOut)
async def get_species(species_id: int, service: SpeciesServiceDep):
    return await service.get_species(species_id)


@router.get("/fishing-methods", response_model=list[FishingMethodOut])
async def list_fishing_methods(service: SpeciesServiceDep):
    return await service.list_methods()
