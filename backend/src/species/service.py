from src.species.exceptions import SpeciesNotFoundError
from src.species.models import FishingMethod
from src.species.repository import SpeciesRepository
from src.species.schemas import SEASON_MONTHS, Season, SpeciesDetail, SpeciesShort, SpeciesSpot
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

    async def get_species(self, species_id: int) -> SpeciesDetail:
        species = await self.repo.get(species_id)
        if species is None:
            raise SpeciesNotFoundError(id=species_id)
        out = await self.images.apply_one(SpeciesDetail.model_validate(species), "image_url")
        spots = await self.repo.list_spots(species.id, active_only=True)
        out.spots = [SpeciesSpot.model_validate(s) for s in spots]
        return out

    async def list_methods(self) -> list[FishingMethod]:
        return await self.repo.list_methods()
