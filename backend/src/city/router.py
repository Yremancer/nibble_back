from fastapi import APIRouter
from src.city.deps import CityServiceDep
from src.city.schemas import CityOut

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get("", response_model=list[CityOut])
async def list_cities(service: CityServiceDep):
    return await service.list_cities()
