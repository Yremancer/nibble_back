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

SCALAR_FIELDS = (
    "name",
    "latin_name",
    "short_description",
    "description",
    "identification",
    "typical_length_cm",
    "typical_weight_g",
    "image_url",
    "aliases",
)


class SpeciesAdminService:
    def __init__(self, repo: SpeciesRepository) -> None:
        self.repo = repo

    async def list_species(self, q: str | None) -> list[SpeciesAdminOut]:
        species = await self.repo.search(q.strip() if q else None, None)
        return [SpeciesAdminOut.model_validate(s) for s in species]

    async def get_species(self, species_id: int) -> SpeciesAdminOut:
        return SpeciesAdminOut.model_validate(await self._require(species_id))

    async def create(self, data: SpeciesCreate) -> SpeciesAdminOut:
        if await self.repo.name_taken(data.name):
            raise SpeciesAlreadyExistsError
        species = Species(
            name=data.name,
            latin_name=data.latin_name,
            short_description=data.short_description,
            description=data.description,
            identification=data.identification,
            typical_length_cm=data.typical_length_cm,
            typical_weight_g=data.typical_weight_g,
            image_url=data.image_url,
            aliases=data.aliases,
            months=[SpeciesMonth(month=m) for m in sorted(data.months)],
        )
        await self.repo.add(species)
        return SpeciesAdminOut.model_validate(species)

    async def update(self, species_id: int, data: SpeciesUpdate) -> SpeciesAdminOut:
        species = await self._require(species_id)
        sent = data.model_fields_set
        if "name" in sent and await self.repo.name_taken(
            data.name, except_id=species.id
        ):
            raise SpeciesAlreadyExistsError
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
        return SpeciesAdminOut.model_validate(species)

    async def delete(self, species_id: int) -> None:
        species = await self._require(species_id)
        used = await self.repo.count_posts_with_species(species.id)
        if used:
            raise SpeciesInUseError(f"Species is used in {used} posts")
        await self.repo.delete(species)

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
