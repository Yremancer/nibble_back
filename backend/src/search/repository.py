from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.species.models import Species
from src.spot.models import Spot

ESCAPE = "\\"


def _escape_like(text: str) -> str:
    # Иначе "%" и "_" в запросе работали бы как подстановочные знаки.
    return (
        text.replace(ESCAPE, ESCAPE * 2).replace("%", ESCAPE + "%").replace("_", ESCAPE + "_")
    )


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def spots(self, q: str, city_id: int | None, limit: int) -> list[Spot]:
        text = _escape_like(q)
        contains = f"%{text}%"
        stmt = select(Spot).where(
            Spot.is_active,
            or_(
                Spot.name.ilike(contains, escape=ESCAPE),
                Spot.area.ilike(contains, escape=ESCAPE),
                func.array_to_string(Spot.aliases, " ").ilike(contains, escape=ESCAPE),
            ),
        )
        if city_id is not None:
            stmt = stmt.where(Spot.city_id == city_id)
        starts = case((Spot.name.ilike(f"{text}%", escape=ESCAPE), 0), else_=1)
        result = await self.session.scalars(stmt.order_by(starts, Spot.name).limit(limit))
        return list(result)

    async def species(self, q: str, limit: int) -> list[Species]:
        text = _escape_like(q)
        contains = f"%{text}%"
        stmt = select(Species).where(
            or_(
                Species.name.ilike(contains, escape=ESCAPE),
                Species.latin_name.ilike(contains, escape=ESCAPE),
                func.array_to_string(Species.aliases, " ").ilike(contains, escape=ESCAPE),
            )
        )
        starts = case((Species.name.ilike(f"{text}%", escape=ESCAPE), 0), else_=1)
        result = await self.session.scalars(
            stmt.order_by(starts, Species.name).limit(limit)
        )
        return list(result)
