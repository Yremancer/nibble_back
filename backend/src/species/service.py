from src.species.exceptions import SpeciesNotFoundError
from src.species.models import FishingMethod
from src.species.repository import SpeciesRepository
from src.species.schemas import SEASON_MONTHS, Season, SpeciesOut, SpeciesShort
from src.storage.images import ImageService


class SpeciesService:
    def __init__(self, repo: SpeciesRepository, images: ImageService) -> None:
        self.repo = repo
        self.images = images

    async def list_species(
        self, q: str | None, season: Season | None
    ) -> list[SpeciesShort]:
        months = SEASON_MONTHS[season] if season else None
        species = await self.repo.search(q.strip() if q else None, months)
        return await self.images.apply(
            [SpeciesShort.model_validate(s) for s in species], "image_url"
        )

    async def get_species(self, species_id: int) -> SpeciesOut:
        species = await self.repo.get(species_id)
        if species is None:
            raise SpeciesNotFoundError(id=species_id)
        return await self.images.apply_one(SpeciesOut.model_validate(species), "image_url")

    async def list_methods(self) -> list[FishingMethod]:
        return await self.repo.list_methods()
