from typing import Annotated

from fastapi import APIRouter, Query
from src.search.deps import SearchServiceDep
from src.search.schemas import SearchQuery, SearchResult

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResult)
async def search(
    query: Annotated[SearchQuery, Query()], service: SearchServiceDep
) -> SearchResult:
    return await service.search(query)
