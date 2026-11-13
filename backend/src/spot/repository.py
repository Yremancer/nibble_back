from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.species.models import FishingMethod, Species
from src.spot.models import Spot, SpotMethod, SpotSpecies


class SpotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        city_id: int | None = None,
        species_id: int | None = None,
        method_id: int | None = None,
    ) -> list[Spot]:
        stmt = select(Spot).where(Spot.is_active)
        if city_id is not None:
            stmt = stmt.where(Spot.city_id == city_id)
        if species_id is not None:
            stmt = stmt.where(
                exists().where(
                    SpotSpecies.spot_id == Spot.id,
                    SpotSpecies.species_id == species_id,
                )
            )
        if method_id is not None:
            stmt = stmt.where(
                exists().where(
                    SpotMethod.spot_id == Spot.id,
                    SpotMethod.method_id == method_id,
                )
            )
        result = await self.session.scalars(stmt.order_by(Spot.name))
        return list(result)

    async def get_active(self, spot_id: int) -> Spot | None:
        return await self.session.scalar(
            select(Spot).where(Spot.id == spot_id, Spot.is_active)
        )

    async def list_species(self, spot_id: int) -> list[Species]:
        result = await self.session.scalars(
            select(Species)
            .join(SpotSpecies, SpotSpecies.species_id == Species.id)
            .where(SpotSpecies.spot_id == spot_id)
            .order_by(Species.name)
        )
        return list(result)

    async def list_methods(self, spot_id: int) -> list[FishingMethod]:
        result = await self.session.scalars(
            select(FishingMethod)
            .join(SpotMethod, SpotMethod.method_id == FishingMethod.id)
            .where(SpotMethod.spot_id == spot_id)
            .order_by(FishingMethod.name)
        )
        return list(result)
