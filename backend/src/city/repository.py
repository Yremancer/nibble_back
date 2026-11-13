from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.city.models import City


class CityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[City]:
        result = await self.session.scalars(select(City).order_by(City.name))
        return list(result)

    async def get(self, city_id: int) -> City | None:
        return await self.session.get(City, city_id)
