from src.species.admin_schemas import (
    MethodCreate,
    MethodUpdate,
    SpeciesAdminOut,
    SpeciesCreate,
    SpeciesUpdate,
)
from src.species.exceptions import (
    MethodAlreadyExistsError,
    MethodInUseError,
    MethodNotFoundError,
    SpeciesAlreadyExistsError,
    SpeciesInUseError,
    SpeciesNotFoundError,
)
from src.species.models import FishingMethod, Species, SpeciesMonth
from src.species.repository import SpeciesRepository
from src.species.schemas import FishingMethodOut
from src.storage.images import ImageService
from src.user.models import User

SCALAR_FIELDS = (
    "name",
    "latin_name",
    "short_description",
    "description",
    "identification",
    "typical_length_cm",
    "typical_weight_g",
    "aliases",
)


class SpeciesAdminService:
    def __init__(self, repo: SpeciesRepository, images: ImageService) -> None:
        self.repo = repo
        self.images = images

    async def list_species(self, q: str | None) -> list[SpeciesAdminOut]:
        species = await self.repo.search(q.strip() if q else None, None)
        return await self.images.apply(
            [SpeciesAdminOut.model_validate(s) for s in species], "image_url"
        )

    async def get_species(self, species_id: int) -> SpeciesAdminOut:
        return await self._out(await self._require(species_id))

    async def create(self, data: SpeciesCreate, staff: User) -> SpeciesAdminOut:
        if await self.repo.name_taken(data.name):
            raise SpeciesAlreadyExistsError
        image = await self.images.claim(data.image_key, staff)
        species = Species(
            name=data.name,
            latin_name=data.latin_name,
            short_description=data.short_description,
            description=data.description,
            identification=data.identification,
            typical_length_cm=data.typical_length_cm,
            typical_weight_g=data.typical_weight_g,
            image_url=image,
            aliases=data.aliases,
            months=[SpeciesMonth(month=m) for m in sorted(data.months)],
        )
        await self.repo.add(species)
        return await self._out(species)

    async def update(
        self, species_id: int, data: SpeciesUpdate, staff: User
    ) -> SpeciesAdminOut:
        species = await self._require(species_id)
        sent = data.model_fields_set
        if "name" in sent and await self.repo.name_taken(
            data.name, except_id=species.id
        ):
            raise SpeciesAlreadyExistsError
        old_image = species.image_url
        if "image_key" in sent:
            species.image_url = await self.images.claim(
                data.image_key, staff, current=old_image
            )
        for field in SCALAR_FIELDS:
            if field in sent:
                setattr(species, field, getattr(data, field))
        if data.months is not None:
            current = {m.month: m for m in species.months}
            species.months = [
                current.get(month) or SpeciesMonth(month=month)
                for month in sorted(data.months)
            ]
        await self.repo.flush()
        if species.image_url != old_image:
            await self.images.release(old_image)
        return await self._out(species)

    async def delete(self, species_id: int) -> None:
        species = await self._require(species_id)
        used = await self.repo.count_posts_with_species(species.id)
        if used:
            raise SpeciesInUseError(f"Species is used in {used} posts")
        image = species.image_url
        await self.repo.delete(species)
        await self.images.release(image)

    async def create_method(self, data: MethodCreate) -> FishingMethodOut:
        if await self.repo.method_name_taken(data.name):
            raise MethodAlreadyExistsError
        method = FishingMethod(name=data.name)
        await self.repo.add_method(method)
        return FishingMethodOut.model_validate(method)

    async def update_method(self, method_id: int, data: MethodUpdate) -> FishingMethodOut:
        method = await self._require_method(method_id)
        if await self.repo.method_name_taken(data.name, except_id=method.id):
            raise MethodAlreadyExistsError
        method.name = data.name
        await self.repo.flush()
        return FishingMethodOut.model_validate(method)

    async def delete_method(self, method_id: int) -> None:
        method = await self._require_method(method_id)
        used = await self.repo.count_posts_with_method(method.id)
        if used:
            raise MethodInUseError(f"Fishing method is used in {used} posts")
        await self.repo.delete_method(method)

    async def _out(self, species: Species) -> SpeciesAdminOut:
        return await self.images.apply_one(SpeciesAdminOut.model_validate(species), "image_url")

    async def _require(self, species_id: int) -> Species:
        species = await self.repo.get(species_id)
        if species is None:
            raise SpeciesNotFoundError(id=species_id)
        return species

    async def _require_method(self, method_id: int) -> FishingMethod:
        method = await self.repo.get_method(method_id)
        if method is None:
            raise MethodNotFoundError(id=method_id)
        return method
