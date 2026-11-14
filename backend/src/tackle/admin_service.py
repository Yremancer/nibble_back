from datetime import UTC, datetime

from src.city.repository import CityRepository
from src.exceptions import ReferenceNotFoundError
from src.models.tackle import TackleCategory, TackleLink, TackleRecommendation
from src.species.repository import SpeciesRepository
from src.tackle.admin_schemas import (
    CategoryAdminOut,
    CategoryCreate,
    CategoryUpdate,
    LinkAdminOut,
    LinkCreate,
    LinkUpdate,
    RecommendationIn,
    RecommendationOut,
)
from src.tackle.exceptions import (
    TackleCategoryAlreadyExistsError,
    TackleCategoryInUseError,
    TackleCategoryNotFoundError,
    TackleLinkNotFoundError,
)
from src.tackle.repository import TackleRepository

LINK_FIELDS = ("category_id", "city_id", "title", "url", "image_url", "sort_order", "is_active")


class TackleAdminService:
    def __init__(
        self,
        repo: TackleRepository,
        cities: CityRepository,
        species: SpeciesRepository,
    ) -> None:
        self.repo = repo
        self.cities = cities
        self.species = species

    async def list_categories(self) -> list[CategoryAdminOut]:
        return [CategoryAdminOut.model_validate(c) for c in await self.repo.list_categories()]

    async def create_category(self, data: CategoryCreate) -> CategoryAdminOut:
        if await self.repo.category_name_taken(data.name):
            raise TackleCategoryAlreadyExistsError
        category = TackleCategory(name=data.name, sort_order=data.sort_order)
        await self.repo.add_category(category)
        return CategoryAdminOut.model_validate(category)

    async def update_category(self, category_id: int, data: CategoryUpdate) -> CategoryAdminOut:
        category = await self._require_category(category_id)
        sent = data.model_fields_set
        if "name" in sent:
            if await self.repo.category_name_taken(data.name, except_id=category.id):
                raise TackleCategoryAlreadyExistsError
            category.name = data.name
        if "sort_order" in sent:
            category.sort_order = data.sort_order
        await self.repo.flush()
        return CategoryAdminOut.model_validate(category)

    async def delete_category(self, category_id: int) -> None:
        category = await self._require_category(category_id)
        used = await self.repo.count_links_in_category(category.id)
        if used:
            raise TackleCategoryInUseError(f"Tackle category has {used} links")
        await self.repo.delete_category(category)

    async def list_links(
        self,
        city_id: int | None,
        category_id: int | None,
        is_active: bool | None,
        q: str | None,
    ) -> list[LinkAdminOut]:
        rows = await self.repo.list_links(
            city_id=city_id,
            category_id=category_id,
            active_only=False,
            is_active=is_active,
            q=q.strip() if q else None,
        )
        recs = await self.repo.recommendations_by_link([link.id for link, _ in rows])
        return [self._out(link, recs[link.id]) for link, _ in rows]

    async def get_link(self, link_id: int) -> LinkAdminOut:
        link = await self._require_link(link_id)
        recs = await self.repo.recommendations_by_link([link.id])
        return self._out(link, recs[link.id])

    async def create_link(self, data: LinkCreate) -> LinkAdminOut:
        await self._check_refs(data.category_id, data.city_id, data.recommendations)
        link = TackleLink(
            category_id=data.category_id,
            city_id=data.city_id,
            title=data.title,
            url=data.url,
            image_url=data.image_url,
            price_from_rub=data.price_from_rub,
            price_updated_at=self._price_moment(data.price_from_rub),
            sort_order=data.sort_order,
            is_active=data.is_active,
        )
        await self.repo.add_link(link)
        recs = await self.repo.replace_recommendations(link.id, self._items(data.recommendations))
        return self._out(link, recs)

    async def update_link(self, link_id: int, data: LinkUpdate) -> LinkAdminOut:
        link = await self._require_link(link_id)
        sent = data.model_fields_set
        await self._check_refs(
            data.category_id if "category_id" in sent else None,
            data.city_id if "city_id" in sent else None,
            data.recommendations or [],
        )
        for field in LINK_FIELDS:
            if field in sent:
                setattr(link, field, getattr(data, field))
        if "price_from_rub" in sent and data.price_from_rub != link.price_from_rub:
            link.price_from_rub = data.price_from_rub
            link.price_updated_at = self._price_moment(data.price_from_rub)
        await self.repo.flush()
        if data.recommendations is not None:
            recs = await self.repo.replace_recommendations(
                link.id, self._items(data.recommendations)
            )
        else:
            recs = (await self.repo.recommendations_by_link([link.id]))[link.id]
        return self._out(link, recs)

    async def delete_link(self, link_id: int) -> None:
        await self.repo.delete_link(await self._require_link(link_id))

    async def _require_category(self, category_id: int) -> TackleCategory:
        category = await self.repo.get_category(category_id)
        if category is None:
            raise TackleCategoryNotFoundError(id=category_id)
        return category

    async def _require_link(self, link_id: int) -> TackleLink:
        link = await self.repo.get_link(link_id)
        if link is None:
            raise TackleLinkNotFoundError(id=link_id)
        return link

    async def _check_refs(
        self,
        category_id: int | None,
        city_id: int | None,
        recommendations: list[RecommendationIn],
    ) -> None:
        if category_id is not None and await self.repo.get_category(category_id) is None:
            raise ReferenceNotFoundError(f"Tackle category not found (id={category_id})")
        if city_id is not None and await self.cities.get(city_id) is None:
            raise ReferenceNotFoundError(f"City not found (id={city_id})")
        species_ids = sorted({r.species_id for r in recommendations if r.species_id is not None})
        method_ids = sorted({r.method_id for r in recommendations if r.method_id is not None})
        if species_ids:
            missing = set(species_ids) - await self.species.existing_ids(species_ids)
            if missing:
                raise ReferenceNotFoundError(f"Species not found: {sorted(missing)}")
        if method_ids:
            missing = set(method_ids) - await self.species.existing_method_ids(method_ids)
            if missing:
                raise ReferenceNotFoundError(f"Fishing methods not found: {sorted(missing)}")

    @staticmethod
    def _price_moment(price: int | None) -> datetime | None:
        return datetime.now(UTC) if price is not None else None

    @staticmethod
    def _items(recommendations: list[RecommendationIn]) -> list[tuple]:
        return [(r.species_id, r.method_id, r.note) for r in recommendations]

    @staticmethod
    def _out(link: TackleLink, recs: list[TackleRecommendation]) -> LinkAdminOut:
        return LinkAdminOut(
            id=link.id,
            category_id=link.category_id,
            city_id=link.city_id,
            title=link.title,
            url=link.url,
            image_url=link.image_url,
            price_from_rub=link.price_from_rub,
            price_updated_at=link.price_updated_at,
            sort_order=link.sort_order,
            is_active=link.is_active,
            recommendations=[RecommendationOut.model_validate(r) for r in recs],
        )
