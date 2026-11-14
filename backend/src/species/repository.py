from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.post.models import Post, PostSpecies
from src.spot.models import Spot, SpotSpecies, SpotSpeciesSource
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

    async def existing_method_ids(self, method_ids: list[int]) -> set[int]:
        result = await self.session.scalars(
            select(FishingMethod.id).where(FishingMethod.id.in_(method_ids))
        )
        return set(result)

    async def name_taken(self, name: str, *, except_id: int | None = None) -> bool:
        stmt = select(Species.id).where(func.lower(Species.name) == name.lower())
        if except_id is not None:
            stmt = stmt.where(Species.id != except_id)
        return await self.session.scalar(stmt.limit(1)) is not None

    async def add(self, species: Species) -> None:
        self.session.add(species)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def delete(self, species: Species) -> None:
        await self.session.delete(species)
        await self.session.flush()

    async def count_posts_with_species(self, species_id: int) -> int:
        return await self.session.scalar(
            select(func.count())
            .select_from(PostSpecies)
            .where(PostSpecies.species_id == species_id)
        )

    async def get_method(self, method_id: int) -> FishingMethod | None:
        return await self.session.get(FishingMethod, method_id)

    async def method_name_taken(
        self, name: str, *, except_id: int | None = None
    ) -> bool:
        stmt = select(FishingMethod.id).where(
            func.lower(FishingMethod.name) == name.lower()
        )
        if except_id is not None:
            stmt = stmt.where(FishingMethod.id != except_id)
        return await self.session.scalar(stmt.limit(1)) is not None

    async def add_method(self, method: FishingMethod) -> None:
        self.session.add(method)
        await self.session.flush()

    async def delete_method(self, method: FishingMethod) -> None:
        await self.session.delete(method)
        await self.session.flush()

    async def count_posts_with_method(self, method_id: int) -> int:
        return await self.session.scalar(
            select(func.count()).select_from(Post).where(Post.method_id == method_id)
        )

    async def list_spots(self, species_id: int, *, active_only: bool) -> list[Spot]:
        stmt = (
            select(Spot)
            .join(SpotSpecies, SpotSpecies.spot_id == Spot.id)
            .where(SpotSpecies.species_id == species_id)
        )
        if active_only:
            stmt = stmt.where(Spot.is_active.is_(True))
        return list(await self.session.scalars(stmt.order_by(Spot.name, Spot.id)))

    async def existing_spot_ids(self, spot_ids: list[int]) -> set[int]:
        result = await self.session.scalars(select(Spot.id).where(Spot.id.in_(spot_ids)))
        return set(result)

    async def replace_spots(self, species_id: int, spot_ids: set[int]) -> None:
        current = set(
            await self.session.scalars(
                select(SpotSpecies.spot_id).where(SpotSpecies.species_id == species_id)
            )
        )
        if current - spot_ids:
            await self.session.execute(
                delete(SpotSpecies).where(
                    SpotSpecies.species_id == species_id,
                    SpotSpecies.spot_id.in_(current - spot_ids),
                )
            )
        self.session.add_all(
            SpotSpecies(
                spot_id=spot_id,
                species_id=species_id,
                data_source=SpotSpeciesSource.MODERATOR.value,
            )
            for spot_id in spot_ids - current
        )
        await self.session.flush()
