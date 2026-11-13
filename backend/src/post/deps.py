from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.post.repository import PostRepository
from src.post.service import PostService
from src.storage.deps import StorageClientDep


def get_post_service(session: SessionDep, storage: StorageClientDep) -> PostService:
    return PostService(PostRepository(session), storage)


PostServiceDep = Annotated[PostService, Depends(get_post_service)]
