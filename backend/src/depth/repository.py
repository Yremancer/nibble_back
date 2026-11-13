from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.depth.models import DepthLayer


class DepthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_city(self, city_id: int) -> list[DepthLayer]:
        result = await self.session.scalars(
            select(DepthLayer)
            .where(DepthLayer.city_id == city_id)
            .order_by(DepthLayer.depth_from)
        )
        return list(result)
