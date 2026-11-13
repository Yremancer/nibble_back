from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.species.models import FishingMethod, Species, SpeciesMonth


class SpeciesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self, q: str | None = None, months: tuple[int, ...] | None = None
    ) -> list[Species]:
        stmt = select(Species).options(selectinload(Species.months))
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(
                    Species.name.ilike(pattern),
                    Species.latin_name.ilike(pattern),
                    func.array_to_string(Species.aliases, " ").ilike(pattern),
                )
            )
        if months:
            stmt = stmt.where(
                exists().where(
                    SpeciesMonth.species_id == Species.id,
                    SpeciesMonth.month.in_(months),
                )
            )
        result = await self.session.scalars(stmt.order_by(Species.name))
        return list(result)

    async def get(self, species_id: int) -> Species | None:
        return await self.session.get(
            Species, species_id, options=[selectinload(Species.months)]
        )

    async def existing_ids(self, species_ids: list[int]) -> set[int]:
        result = await self.session.scalars(
            select(Species.id).where(Species.id.in_(species_ids))
        )
        return set(result)

    async def method_exists(self, method_id: int) -> bool:
        return await self.session.get(FishingMethod, method_id) is not None

    async def list_methods(self) -> list[FishingMethod]:
        result = await self.session.scalars(
            select(FishingMethod).order_by(FishingMethod.name)
        )
        return list(result)
