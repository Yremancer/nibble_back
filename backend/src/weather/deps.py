from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request
from src.database.deps import SessionDep
from src.settings import settings
from src.weather.client import OpenMeteoClient
from src.weather.repository import WeatherRepository
from src.weather.service import WeatherService


def get_weather_client(request: Request) -> OpenMeteoClient:
    return OpenMeteoClient(request.app.state.http)


def get_weather_service(
    session: SessionDep,
    client: Annotated[OpenMeteoClient, Depends(get_weather_client)],
) -> WeatherService:
    return WeatherService(
        WeatherRepository(session),
        client,
        timedelta(minutes=settings.WEATHER_CACHE_TTL_MINUTES),
    )


WeatherServiceDep = Annotated[WeatherService, Depends(get_weather_service)]
