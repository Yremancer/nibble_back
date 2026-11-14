from src.search.repository import SearchRepository
from src.search.schemas import SearchQuery, SearchResult, SpeciesHit
from src.spot.schemas import SpotShort
from src.storage.images import ImageService


class SearchService:
    def __init__(self, repo: SearchRepository, images: ImageService) -> None:
        self.repo = repo
        self.images = images

    async def search(self, query: SearchQuery) -> SearchResult:
        spots = await self.repo.spots(query.q, query.city_id, query.limit)
        species = await self.repo.species(query.q, query.limit)
        return SearchResult(
            spots=await self.images.apply(
                [SpotShort.model_validate(s) for s in spots], "photo_url"
            ),
            species=await self.images.apply(
                [SpeciesHit.model_validate(s) for s in species], "image_url"
            ),
        )
