from src.species.schemas import FishingMethodOut
from src.spot.exceptions import SpotNotFoundError
from src.spot.models import Spot
from src.spot.repository import SpotRepository
from src.spot.schemas import SpotOut, SpotShort, SpotSpeciesOut


class SpotService:
    def __init__(self, repo: SpotRepository) -> None:
        self.repo = repo

    async def list_spots(
        self, city_id: int | None, species_id: int | None, method_id: int | None
    ) -> list[Spot]:
        return await self.repo.search(city_id, species_id, method_id)

    async def get_spot(self, spot_id: int) -> SpotOut:
        spot = await self.repo.get_active(spot_id)
        if spot is None:
            raise SpotNotFoundError(id=spot_id)
        species = await self.repo.list_species(spot_id)
        methods = await self.repo.list_methods(spot_id)
        return SpotOut(
            **SpotShort.model_validate(spot).model_dump(),
            description=spot.description,
            species=[SpotSpeciesOut.model_validate(s) for s in species],
            methods=[FishingMethodOut.model_validate(m) for m in methods],
        )
