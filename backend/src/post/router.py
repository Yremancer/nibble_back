from typing import Annotated

from fastapi import APIRouter, Query, status
from src.auth.deps import CurrentUserDep, OptionalUserDep
from src.post.deps import PostServiceDep
from src.post.schemas import (
    CommentCreate,
    CommentOut,
    CommentPage,
    FeedQuery,
    PostCreate,
    PostOut,
    PostPage,
    PostUpdate,
)

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=PostPage)
async def get_feed(
    query: Annotated[FeedQuery, Query()],
    viewer: OptionalUserDep,
    service: PostServiceDep,
) -> PostPage:
    return await service.get_feed(query, viewer)


@router.post("", response_model=PostOut, status_code=status.HTTP_201_CREATED)
async def create_post(
    data: PostCreate, user: CurrentUserDep, service: PostServiceDep
) -> PostOut:
    return await service.create(data, user)


@router.get("/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int, viewer: OptionalUserDep, service: PostServiceDep
) -> PostOut:
    return await service.get_post(post_id, viewer)


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


@router.post("/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def like_post(
    post_id: int, user: CurrentUserDep, service: PostServiceDep
) -> None:
    await service.like(post_id, user)


@router.delete("/{post_id}/like", status_code=status.HTTP_204_NO_CONTENT)
async def unlike_post(
    post_id: int, user: CurrentUserDep, service: PostServiceDep
) -> None:
    await service.unlike(post_id, user)


@router.get(
    "/{post_id}/comments",
    response_model=CommentPage,
    description="Комментарии и ответы по возрастанию ID.",
)
async def get_comments(
    post_id: int, service: PostServiceDep, cursor: int | None = None, limit: int = 20
) -> CommentPage:
    return await service.get_comments(post_id, cursor, limit)


@router.post(
    "/{post_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    post_id: int, data: CommentCreate, user: CurrentUserDep, service: PostServiceDep
) -> CommentOut:
    return await service.create_comment(post_id, data, user)


@router.delete(
    "/{post_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    description=("Автор удаляет свой комментарий, модератор и админ — любой."),
)
async def delete_comment(
    post_id: int, comment_id: int, user: CurrentUserDep, service: PostServiceDep
) -> None:
    await service.delete_comment(post_id, comment_id, user)
