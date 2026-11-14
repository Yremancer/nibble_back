from src.species.schemas import FishingMethodOut
from src.spot.exceptions import SpotNotFoundError
from src.spot.repository import SpotRepository
from src.spot.schemas import SpotOut, SpotShort, SpotSpeciesOut
from src.storage.images import ImageService


class SpotService:
    def __init__(self, repo: SpotRepository, images: ImageService) -> None:
        self.repo = repo
        self.images = images

    async def list_spots(
        self, city_id: int | None, species_id: int | None, method_id: int | None
    ) -> list[SpotShort]:
        spots = await self.repo.search(city_id, species_id, method_id)
        return await self.images.apply(
            [SpotShort.model_validate(s) for s in spots], "photo_url"
        )

    async def get_spot(self, spot_id: int) -> SpotOut:
        spot = await self.repo.get_active(spot_id)
        if spot is None:
            raise SpotNotFoundError(id=spot_id)
        species = await self.repo.list_species(spot_id)
        methods = await self.repo.list_methods(spot_id)
        short = await self.images.apply_one(SpotShort.model_validate(spot), "photo_url")
        return SpotOut(
            **short.model_dump(),
            description=spot.description,
            species=await self.images.apply(
                [SpotSpeciesOut.model_validate(s) for s in species], "image_url"
            ),
            methods=[FishingMethodOut.model_validate(m) for m in methods],
        )
