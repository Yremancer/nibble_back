from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.search.repository import SearchRepository
from src.search.service import SearchService
from src.storage.deps import ImageServiceDep


def get_search_service(session: SessionDep, images: ImageServiceDep) -> SearchService:
    return SearchService(SearchRepository(session), images)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
