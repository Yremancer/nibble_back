from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import City, Spot
from src.weather.client import WeatherData
from src.weather.models import WeatherCurrent, WeatherForecast

UPDATED_COLUMNS = ("temp_c", "condition", "wind_dir", "wind_speed_ms", "provider", "fetched_at")


@dataclass(frozen=True)
class Location:
    name: str
    lat: Decimal
    lon: Decimal
    timezone: str


class WeatherRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_city_location(self, city_id: int) -> Location | None:
        row = (
            await self.session.execute(
                select(City.name, City.lat, City.lon, City.timezone).where(
                    City.id == city_id
                )
            )
        ).one_or_none()
        return Location(*row) if row else None

    async def get_spot_location(self, spot_id: int) -> Location | None:
        row = (
            await self.session.execute(
                select(Spot.name, Spot.lat, Spot.lon, City.timezone)
                .join(City, City.id == Spot.city_id)
                .where(Spot.id == spot_id)
            )
        ).one_or_none()
        return Location(*row) if row else None

    async def get_current(
        self, city_id: int | None, spot_id: int | None
    ) -> WeatherCurrent | None:
        return await self.session.scalar(
            select(WeatherCurrent)
            .where(_target(WeatherCurrent, city_id, spot_id))
            .execution_options(populate_existing=True)
        )

    async def list_forecasts(
        self, city_id: int | None, spot_id: int | None, date_from: date, days: int
    ) -> list[WeatherForecast]:
        result = await self.session.scalars(
            select(WeatherForecast)
            .where(
                _target(WeatherForecast, city_id, spot_id),
                WeatherForecast.forecast_date >= date_from,
                WeatherForecast.forecast_date < date_from + timedelta(days=days),
            )
            .order_by(WeatherForecast.forecast_date)
            .execution_options(populate_existing=True)
        )
        return list(result)

    async def save(
        self,
        city_id: int | None,
        spot_id: int | None,
        data: WeatherData,
        provider: str,
        fetched_at: datetime,
    ) -> None:
        common = {
            "city_id": city_id,
            "spot_id": spot_id,
            "provider": provider,
            "fetched_at": fetched_at,
        }
        key = "city_id" if city_id is not None else "spot_id"
        await self._upsert(WeatherCurrent, [asdict(data.current) | common], [key])
        if data.days:
            await self._upsert(
                WeatherForecast,
                [asdict(day) | common for day in data.days],
                [key, "forecast_date"],
            )

    async def _upsert(self, model: type, rows: list[dict], keys: list[str]) -> None:
        stmt = insert(model).values(rows)
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=keys,
                set_={column: stmt.excluded[column] for column in UPDATED_COLUMNS},
            )
        )


def _target(model: type[WeatherCurrent] | type[WeatherForecast], city_id, spot_id):
    if city_id is not None:
        return model.city_id == city_id
    return model.spot_id == spot_id
