from typing import Annotated

from fastapi import APIRouter, Query, status
from src.auth.deps import CurrentUserDep
from src.post.deps import PostServiceDep
from src.post.schemas import FeedQuery, PostCreate, PostOut, PostPage, PostUpdate

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=PostPage)
async def get_feed(
    query: Annotated[FeedQuery, Query()], service: PostServiceDep
) -> PostPage:
    return await service.get_feed(query)


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    data: PostCreate, user: CurrentUserDep, service: PostServiceDep
) -> PostOut:
    return await service.create(data, user)


@router.get("/{post_id}", response_model=PostOut)
async def get_post(post_id: int, service: PostServiceDep) -> PostOut:
    return await service.get_post(post_id)


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int, data: PostUpdate, user: CurrentUserDep, service: PostServiceDep
) -> PostOut:
    return await service.update(post_id, data, user)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int, user: CurrentUserDep, service: PostServiceDep
) -> None:
    await service.delete(post_id, user)
