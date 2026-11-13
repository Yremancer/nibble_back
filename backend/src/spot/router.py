from fastapi import APIRouter
from src.spot.deps import SpotServiceDep
from src.spot.schemas import SpotOut, SpotShort

router = APIRouter(prefix="/spots", tags=["spots"])


@router.get("", response_model=list[SpotShort])
async def list_spots(
    service: SpotServiceDep,
    city_id: int | None = None,
    species_id: int | None = None,
    method_id: int | None = None,
):
    return await service.list_spots(city_id, species_id, method_id)


@router.get("/{spot_id}", response_model=SpotOut)
async def get_spot(spot_id: int, service: SpotServiceDep):
    return await service.get_spot(spot_id)
