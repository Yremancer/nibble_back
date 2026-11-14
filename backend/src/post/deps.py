from typing import Annotated

from fastapi import Depends
from src.city.repository import CityRepository
from src.database.deps import SessionDep
from src.post.moderation_service import PostModerationService
from src.post.repository import PostRepository
from src.post.service import PostService
from src.species.repository import SpeciesRepository
from src.spot.repository import SpotRepository
from src.storage.deps import StorageClientDep
from src.storage.repository import FileRepository


def _dependencies(session: SessionDep, storage: StorageClientDep) -> tuple:
    return (
        PostRepository(session),
        SpotRepository(session),
        SpeciesRepository(session),
        FileRepository(session),
        CityRepository(session),
        storage,
    )


def get_post_service(session: SessionDep, storage: StorageClientDep) -> PostService:
    return PostService(*_dependencies(session, storage))


PostServiceDep = Annotated[PostService, Depends(get_post_service)]


def get_moderation_service(
    session: SessionDep, storage: StorageClientDep
) -> PostModerationService:
    return PostModerationService(*_dependencies(session, storage))


PostModerationServiceDep = Annotated[
    PostModerationService, Depends(get_moderation_service)
]
