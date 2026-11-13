from typing import Annotated

from fastapi import Depends
from src.city.repository import CityRepository
from src.database.deps import SessionDep
from src.post.repository import PostRepository
from src.post.service import PostService
from src.species.repository import SpeciesRepository
from src.spot.repository import SpotRepository
from src.storage.deps import StorageClientDep
from src.storage.repository import FileRepository


def get_post_service(session: SessionDep, storage: StorageClientDep) -> PostService:
    return PostService(
        PostRepository(session),
        SpotRepository(session),
        SpeciesRepository(session),
        FileRepository(session),
        CityRepository(session),
        storage,
    )


PostServiceDep = Annotated[PostService, Depends(get_post_service)]
