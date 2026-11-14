from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.species.models import FishingMethod, Species
from src.spot.models import Spot, SpotMethod, SpotSpecies, SpotSpeciesSource


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

    async def admin_list(
        self, city_id: int | None, is_active: bool | None, q: str | None
    ) -> list[Spot]:
        stmt = select(Spot)
        if city_id is not None:
            stmt = stmt.where(Spot.city_id == city_id)
        if is_active is not None:
            stmt = stmt.where(Spot.is_active == is_active)
        if q:
            stmt = stmt.where(Spot.name.ilike(f"%{q}%"))
        result = await self.session.scalars(stmt.order_by(Spot.name, Spot.id))
        return list(result)

    async def get_any(self, spot_id: int) -> Spot | None:
        return await self.session.get(Spot, spot_id)

    async def name_taken(
        self, city_id: int, name: str, *, except_id: int | None = None
    ) -> bool:
        stmt = select(Spot.id).where(
            Spot.city_id == city_id, func.lower(Spot.name) == name.lower()
        )
        if except_id is not None:
            stmt = stmt.where(Spot.id != except_id)
        return await self.session.scalar(stmt.limit(1)) is not None

    async def add(self, spot: Spot) -> None:
        self.session.add(spot)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def replace_species(self, spot_id: int, species_ids: set[int]) -> None:
        current = set(
            await self.session.scalars(
                select(SpotSpecies.species_id).where(SpotSpecies.spot_id == spot_id)
            )
        )
        if current - species_ids:
            await self.session.execute(
                delete(SpotSpecies).where(
                    SpotSpecies.spot_id == spot_id,
                    SpotSpecies.species_id.in_(current - species_ids),
                )
            )
        self.session.add_all(
            SpotSpecies(
                spot_id=spot_id,
                species_id=species_id,
                data_source=SpotSpeciesSource.MODERATOR.value,
            )
            for species_id in species_ids - current
        )
        await self.session.flush()

    async def replace_methods(self, spot_id: int, method_ids: set[int]) -> None:
        current = set(
            await self.session.scalars(
                select(SpotMethod.method_id).where(SpotMethod.spot_id == spot_id)
            )
        )
        if current - method_ids:
            await self.session.execute(
                delete(SpotMethod).where(
                    SpotMethod.spot_id == spot_id,
                    SpotMethod.method_id.in_(current - method_ids),
                )
            )
        self.session.add_all(
            SpotMethod(spot_id=spot_id, method_id=method_id)
            for method_id in method_ids - current
        )
        await self.session.flush()
