from typing import Annotated

from fastapi import APIRouter, Query
from src.auth.deps import ModeratorDep
from src.post.deps import PostModerationServiceDep
from src.post.schemas import (
    AdminCommentOut,
    AdminCommentPage,
    AdminPostOut,
    AdminPostPage,
    AdminPostQuery,
    AdminPostUpdate,
    CommentHide,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/posts",
    response_model=AdminPostPage,
    description="Посты любого статуса. status=moderation: очередь на проверку.",
)
async def list_posts(
    query: Annotated[AdminPostQuery, Query()],
    staff: ModeratorDep,
    service: PostModerationServiceDep,
) -> AdminPostPage:
    return await service.moderation_feed(query, staff)


@router.get("/posts/{post_id}", response_model=AdminPostOut)
async def get_post(
    post_id: int, staff: ModeratorDep, service: PostModerationServiceDep
) -> AdminPostOut:
    return await service.moderation_post(post_id, staff)


@router.patch(
    "/posts/{post_id}",
    response_model=AdminPostOut,
    description=(
        "Статус (published, hidden, moderation) для любых постов. "
        "spot_id, method_id и species только для импортированных. "
        "Изменённые поля повторный импорт не перезаписывает."
    ),
)
async def moderate_post(
    post_id: int,
    data: AdminPostUpdate,
    staff: ModeratorDep,
    service: PostModerationServiceDep,
) -> AdminPostOut:
    return await service.moderate(post_id, data, staff)


@router.get("/posts/{post_id}/comments", response_model=AdminCommentPage)
async def list_comments(
    post_id: int,
    _staff: ModeratorDep,
    service: PostModerationServiceDep,
    cursor: int | None = None,
    limit: int = 20,
) -> AdminCommentPage:
    return await service.moderation_comments(post_id, cursor, limit)


@router.patch("/comments/{comment_id}", response_model=AdminCommentOut)
async def hide_comment(
    comment_id: int,
    data: CommentHide,
    _staff: ModeratorDep,
    service: PostModerationServiceDep,
) -> AdminCommentOut:
    return await service.set_comment_hidden(comment_id, data.is_hidden)
