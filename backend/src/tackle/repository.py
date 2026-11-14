from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tackle import TackleCategory, TackleLink, TackleRecommendation


def applies(rec: TackleRecommendation, species_id: int | None, method_id: int | None) -> bool:
    if species_id is not None and method_id is not None:
        return rec.species_id in (species_id, None) and rec.method_id in (method_id, None)
    if species_id is not None:
        return rec.species_id == species_id
    if method_id is not None:
        return rec.method_id == method_id
    return True


def _applies_sql(species_id: int | None, method_id: int | None):
    if species_id is not None and method_id is not None:
        return and_(
            or_(TackleRecommendation.species_id == species_id, TackleRecommendation.species_id.is_(None)),
            or_(TackleRecommendation.method_id == method_id, TackleRecommendation.method_id.is_(None)),
        )
    if species_id is not None:
        return TackleRecommendation.species_id == species_id
    return TackleRecommendation.method_id == method_id


class TackleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_categories(self) -> list[TackleCategory]:
        result = await self.session.scalars(
            select(TackleCategory).order_by(TackleCategory.sort_order, TackleCategory.name)
        )
        return list(result)

    async def list_links(
        self,
        *,
        city_id: int | None = None,
        category_id: int | None = None,
        species_id: int | None = None,
        method_id: int | None = None,
        active_only: bool = True,
        is_active: bool | None = None,
        q: str | None = None,
        limit: int | None = None,
    ) -> list[tuple[TackleLink, TackleCategory]]:
        stmt = select(TackleLink, TackleCategory).join(
            TackleCategory, TackleCategory.id == TackleLink.category_id
        )
        if active_only:
            stmt = stmt.where(TackleLink.is_active)
        elif is_active is not None:
            stmt = stmt.where(TackleLink.is_active == is_active)
        if city_id is not None:
            stmt = stmt.where(TackleLink.city_id == city_id)
        if category_id is not None:
            stmt = stmt.where(TackleLink.category_id == category_id)
        if q:
            stmt = stmt.where(TackleLink.title.ilike(f"%{q}%"))
        if species_id is not None or method_id is not None:
            stmt = stmt.where(
                exists().where(
                    TackleRecommendation.link_id == TackleLink.id,
                    _applies_sql(species_id, method_id),
                )
            )
        stmt = stmt.order_by(
            TackleCategory.sort_order, TackleLink.sort_order, TackleLink.title, TackleLink.id
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return [(link, category) for link, category in await self.session.execute(stmt)]

    async def recommendations_by_link(
        self, link_ids: list[int]
    ) -> dict[int, list[TackleRecommendation]]:
        grouped: dict[int, list[TackleRecommendation]] = {i: [] for i in link_ids}
        if not link_ids:
            return grouped
        result = await self.session.scalars(
            select(TackleRecommendation)
            .where(TackleRecommendation.link_id.in_(link_ids))
            .order_by(TackleRecommendation.id)
        )
        for rec in result:
            grouped[rec.link_id].append(rec)
        return grouped

    async def get_category(self, category_id: int) -> TackleCategory | None:
        return await self.session.get(TackleCategory, category_id)

    async def category_name_taken(self, name: str, *, except_id: int | None = None) -> bool:
        stmt = select(TackleCategory.id).where(func.lower(TackleCategory.name) == name.lower())
        if except_id is not None:
            stmt = stmt.where(TackleCategory.id != except_id)
        return await self.session.scalar(stmt.limit(1)) is not None

    async def add_category(self, category: TackleCategory) -> None:
        self.session.add(category)
        await self.session.flush()

    async def delete_category(self, category: TackleCategory) -> None:
        await self.session.delete(category)
        await self.session.flush()

    async def count_links_in_category(self, category_id: int) -> int:
        return await self.session.scalar(
            select(func.count()).select_from(TackleLink).where(TackleLink.category_id == category_id)
        )

    async def get_link(self, link_id: int) -> TackleLink | None:
        return await self.session.get(TackleLink, link_id)

    async def add_link(self, link: TackleLink) -> None:
        self.session.add(link)
        await self.session.flush()

    async def delete_link(self, link: TackleLink) -> None:
        await self.session.delete(link)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def replace_recommendations(
        self, link_id: int, items: list[tuple[int | None, int | None, str | None]]
    ) -> list[TackleRecommendation]:
        await self.session.execute(
            delete(TackleRecommendation).where(TackleRecommendation.link_id == link_id)
        )
        recs = [
            TackleRecommendation(link_id=link_id, species_id=s, method_id=m, note=note)
            for s, m, note in items
        ]
        self.session.add_all(recs)
        await self.session.flush()
        return recs
