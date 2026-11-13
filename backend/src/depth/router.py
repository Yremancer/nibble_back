from fastapi import APIRouter, Response
from src.depth.deps import DepthServiceDep
from src.depth.schemas import DepthZones

router = APIRouter(prefix="/depths", tags=["depths"])

# Зоны меняются только при перезаливке данных, браузеру можно держать их сутки.
CACHE_CONTROL = "public, max-age=86400"


@router.get("", response_model=DepthZones)
async def get_depths(city_id: int, service: DepthServiceDep, response: Response):
    response.headers["Cache-Control"] = CACHE_CONTROL
    return await service.get_zones(city_id)
