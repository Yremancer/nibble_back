from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from src.weather.client import PROVIDER, OpenMeteoClient
from src.weather.exceptions import (
    CityNotFoundError,
    SpotNotFoundError,
    WeatherUnavailableError,
)
from src.weather.repository import Location, WeatherRepository
from src.weather.schemas import WeatherDay, WeatherNow, WeatherResponse

FORECAST_DAYS = 5


class WeatherService:
    def __init__(
        self, repository: WeatherRepository, client: OpenMeteoClient, cache_ttl: timedelta
    ) -> None:
        self.repository = repository
        self.client = client
        self.cache_ttl = cache_ttl

    async def get_weather(self, city_id: int | None, spot_id: int | None) -> WeatherResponse:
        location = await self._get_location(city_id, spot_id)
        today = datetime.now(ZoneInfo(location.timezone)).date()
        now = datetime.now(UTC)

        current, days = await self._read_cache(city_id, spot_id, today)
        cached = [current, *days] if current else days
        is_fresh = (
            current is not None
            and len(days) == FORECAST_DAYS
            and all(now - row.fetched_at < self.cache_ttl for row in cached)
        )
        if not is_fresh:
            try:
                data = await self.client.fetch(
                    location.lat, location.lon, location.timezone, FORECAST_DAYS
                )
            except WeatherUnavailableError:
                if not cached:
                    raise
            else:
                await self.repository.save(city_id, spot_id, data, PROVIDER, now)
                current, days = await self._read_cache(city_id, spot_id, today)
                cached = [current, *days] if current else days

        return WeatherResponse(
            name=location.name,
            city_id=city_id,
            spot_id=spot_id,
            fetched_at=min((row.fetched_at for row in cached), default=None),
            current=WeatherNow.model_validate(current) if current else None,
            days=[WeatherDay.model_validate(day) for day in days],
        )

    async def _read_cache(self, city_id, spot_id, today):
        current = await self.repository.get_current(city_id, spot_id)
        days = await self.repository.list_forecasts(city_id, spot_id, today, FORECAST_DAYS)
        return current, days

    async def _get_location(self, city_id: int | None, spot_id: int | None) -> Location:
        if city_id is not None:
            location = await self.repository.get_city_location(city_id)
            if location is None:
                raise CityNotFoundError(id=city_id)
            return location
        location = await self.repository.get_spot_location(spot_id)
        if location is None:
            raise SpotNotFoundError(id=spot_id)
        return location
