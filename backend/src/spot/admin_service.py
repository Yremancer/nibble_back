from src.city.repository import CityRepository
from src.exceptions import ReferenceNotFoundError
from src.species.repository import SpeciesRepository
from src.species.schemas import FishingMethodOut
from src.spot.admin_schemas import SpotAdminItem, SpotAdminOut, SpotCreate, SpotUpdate
from src.spot.exceptions import SpotAlreadyExistsError, SpotNotFoundError
from src.spot.models import Spot
from src.spot.repository import SpotRepository
from src.spot.schemas import SpotSpeciesOut
from src.storage.images import ImageService
from src.user.models import User

SCALAR_FIELDS = (
    "city_id",
    "name",
    "area",
    "description",
    "lat",
    "lon",
    "aliases",
    "is_active",
)


class SpotAdminService:
    def __init__(
        self,
        repo: SpotRepository,
        cities: CityRepository,
        species: SpeciesRepository,
        images: ImageService,
    ) -> None:
        self.repo = repo
        self.cities = cities
        self.species = species
        self.images = images

    async def list_spots(
        self, city_id: int | None, is_active: bool | None, q: str | None
    ) -> list[SpotAdminItem]:
        spots = await self.repo.admin_list(city_id, is_active, q.strip() if q else None)
        return await self.images.apply(
            [SpotAdminItem.model_validate(s) for s in spots], "photo_url"
        )

    async def get_spot(self, spot_id: int) -> SpotAdminOut:
        return await self._out(await self._require(spot_id))

    async def create(self, data: SpotCreate, actor: User) -> SpotAdminOut:
        await self._check_refs(data.city_id, data.species_ids, data.method_ids)
        if await self.repo.name_taken(data.city_id, data.name):
            raise SpotAlreadyExistsError
        photo = await self.images.claim(data.photo_key, actor) if data.photo_key else None
        spot = Spot(
            city_id=data.city_id,
            name=data.name,
            area=data.area,
            description=data.description,
            lat=data.lat,
            lon=data.lon,
            photo_url=photo,
            aliases=data.aliases,
            is_active=data.is_active,
            created_by=actor.id,
        )
        await self.repo.add(spot)
        await self.repo.replace_species(spot.id, set(data.species_ids))
        await self.repo.replace_methods(spot.id, set(data.method_ids))
        return await self._out(spot)

    async def update(self, spot_id: int, data: SpotUpdate, actor: User) -> SpotAdminOut:
        spot = await self._require(spot_id)
        sent = data.model_fields_set
        await self._check_refs(
            data.city_id if "city_id" in sent else None,
            data.species_ids if "species_ids" in sent else [],
            data.method_ids if "method_ids" in sent else [],
        )
        city_id = data.city_id if "city_id" in sent else spot.city_id
        name = data.name if "name" in sent else spot.name
        if ("city_id" in sent or "name" in sent) and await self.repo.name_taken(
            city_id, name, except_id=spot.id
        ):
            raise SpotAlreadyExistsError
        old_photo = spot.photo_url
        if "photo_key" in sent:
            spot.photo_url = (
                await self.images.claim(data.photo_key, actor, current=old_photo)
                if data.photo_key
                else None
            )
        for field in SCALAR_FIELDS:
            if field in sent:
                setattr(spot, field, getattr(data, field))
        await self.repo.flush()
        if spot.photo_url != old_photo:
            await self.images.release(old_photo)
        if data.species_ids is not None:
            await self.repo.replace_species(spot.id, set(data.species_ids))
        if data.method_ids is not None:
            await self.repo.replace_methods(spot.id, set(data.method_ids))
        return await self._out(spot)

    async def deactivate(self, spot_id: int) -> None:
        spot = await self._require(spot_id)
        spot.is_active = False
        await self.repo.flush()

    async def _require(self, spot_id: int) -> Spot:
        spot = await self.repo.get_any(spot_id)
        if spot is None:
            raise SpotNotFoundError(id=spot_id)
        return spot

    async def _check_refs(
        self, city_id: int | None, species_ids: list[int], method_ids: list[int]
    ) -> None:
        if city_id is not None and await self.cities.get(city_id) is None:
            raise ReferenceNotFoundError(f"City not found (id={city_id})")
        if species_ids:
            missing = set(species_ids) - await self.species.existing_ids(species_ids)
            if missing:
                raise ReferenceNotFoundError(f"Species not found: {sorted(missing)}")
        if method_ids:
            missing = set(method_ids) - await self.species.existing_method_ids(method_ids)
            if missing:
                raise ReferenceNotFoundError(f"Fishing methods not found: {sorted(missing)}")

    async def _out(self, spot: Spot) -> SpotAdminOut:
        species = await self.repo.list_species(spot.id)
        methods = await self.repo.list_methods(spot.id)
        item = await self.images.apply_one(SpotAdminItem.model_validate(spot), "photo_url")
        return SpotAdminOut(
            **item.model_dump(),
            description=spot.description,
            aliases=spot.aliases or [],
            species=await self.images.apply(
                [SpotSpeciesOut.model_validate(s) for s in species], "image_url"
            ),
            methods=[FishingMethodOut.model_validate(m) for m in methods],
        )
