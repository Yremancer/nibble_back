from typing import Annotated

from fastapi import APIRouter, Query
from src.weather.deps import WeatherServiceDep
from src.weather.schemas import WeatherQuery, WeatherResponse

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("", response_model=WeatherResponse)
async def get_weather(
    query: Annotated[WeatherQuery, Query()], service: WeatherServiceDep
) -> WeatherResponse:
    return await service.get_weather(query.city_id, query.spot_id)
