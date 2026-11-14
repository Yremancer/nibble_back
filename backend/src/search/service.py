from src.search.repository import SearchRepository
from src.search.schemas import SearchQuery, SearchResult, SpeciesHit
from src.spot.schemas import SpotShort


class SearchService:
    def __init__(self, repo: SearchRepository) -> None:
        self.repo = repo

    async def search(self, query: SearchQuery) -> SearchResult:
        spots = await self.repo.spots(query.q, query.city_id, query.limit)
        species = await self.repo.species(query.q, query.limit)
        return SearchResult(
            spots=[SpotShort.model_validate(s) for s in spots],
            species=[SpeciesHit.model_validate(s) for s in species],
        )
