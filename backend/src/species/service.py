from src.species.exceptions import SpeciesNotFoundError
from src.species.models import FishingMethod, Species
from src.species.repository import SpeciesRepository
from src.species.schemas import SEASON_MONTHS, Season


class SpeciesService:
    def __init__(self, repo: SpeciesRepository) -> None:
        self.repo = repo

    async def list_species(
        self, q: str | None, season: Season | None
    ) -> list[Species]:
        months = SEASON_MONTHS[season] if season else None
        return await self.repo.search(q.strip() if q else None, months)

    async def get_species(self, species_id: int) -> Species:
        species = await self.repo.get(species_id)
        if species is None:
            raise SpeciesNotFoundError(id=species_id)
        return species

    async def list_methods(self) -> list[FishingMethod]:
        return await self.repo.list_methods()
