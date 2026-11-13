from typing import Annotated

from fastapi import APIRouter, Query
from src.post.deps import PostServiceDep
from src.post.schemas import FeedQuery, PostOut, PostPage

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=PostPage)
async def get_feed(
    query: Annotated[FeedQuery, Query()], service: PostServiceDep
) -> PostPage:
    return await service.get_feed(query)


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: int, service: PostServiceDep) -> PostOut:
    return await service.get_post(post_id)
