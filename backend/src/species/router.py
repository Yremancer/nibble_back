from fastapi import APIRouter
from src.species.deps import SpeciesServiceDep
from src.species.schemas import FishingMethodOut, Season, SpeciesDetail, SpeciesShort

router = APIRouter(tags=["species"])


@router.get("/species", response_model=list[SpeciesShort])
async def list_species(
    service: SpeciesServiceDep,
    q: str | None = None,
    season: Season | None = None,
):
    return await service.list_species(q, season)


@router.get("/species/{species_id}", response_model=SpeciesDetail)
async def get_species(species_id: int, service: SpeciesServiceDep):
    return await service.get_species(species_id)


@router.get("/fishing-methods", response_model=list[FishingMethodOut])
async def list_fishing_methods(service: SpeciesServiceDep):
    return await service.list_methods()
