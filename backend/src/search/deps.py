from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.search.repository import SearchRepository
from src.search.service import SearchService


def get_search_service(session: SessionDep) -> SearchService:
    return SearchService(SearchRepository(session))


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
