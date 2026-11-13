from datetime import datetime
from typing import NamedTuple

from sqlalchemy import Select, delete, exists, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.models.media import PostMedia
from src.post.models import (
    Comment,
    Post,
    PostLike,
    PostSpecies,
    PostStatus,
    Source,
    SourceType,
)
from src.post.schemas import FeedQuery
from src.spot.models import Spot
from src.user.models import User


class PostEngagement(NamedTuple):
    likes_count: int
    comments_count: int
    liked_by_me: bool


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _with_card_data(stmt: Select[tuple[Post]]) -> Select[tuple[Post]]:
        return stmt.options(
            selectinload(Post.source),
            selectinload(Post.author),
            selectinload(Post.spot),
            selectinload(Post.method),
            selectinload(Post.media).selectinload(PostMedia.media_file),
            selectinload(Post.catches).selectinload(PostSpecies.species),
        )

    @classmethod
    def _visible(cls) -> Select[tuple[Post]]:
        return cls._with_card_data(
            select(Post)
            .join(Source, Source.id == Post.source_id)
            .outerjoin(Spot, Spot.id == Post.spot_id)
            .outerjoin(User, User.id == Post.author_id)
            .where(
                Post.status == PostStatus.PUBLISHED.value,
                Post.canonical_post_id.is_(None),
            )
        )

    async def feed(
        self, query: FeedQuery, after: tuple[datetime, int] | None
    ) -> list[Post]:
        stmt = self._visible()
        if query.city_id is not None:
            stmt = stmt.where(
                func.coalesce(Spot.city_id, User.city_id, Source.city_id)
                == query.city_id
            )
        if query.source is not None:
            stmt = stmt.where(Source.type == query.source.value)
        if query.spot_id is not None:
            stmt = stmt.where(Post.spot_id == query.spot_id, Post.show_spot)
        if query.species_id is not None:
            stmt = stmt.where(
                exists().where(
                    PostSpecies.post_id == Post.id,
                    PostSpecies.species_id == query.species_id,
                )
            )
        if query.kind is not None:
            stmt = stmt.where(Post.kind == query.kind.value)
        if after is not None:
            stmt = stmt.where(tuple_(Post.published_at, Post.id) < tuple_(*after))
        stmt = stmt.order_by(Post.published_at.desc(), Post.id.desc()).limit(
            query.limit + 1
        )
        return list(await self.session.scalars(stmt))

    async def get_visible(self, post_id: int) -> Post | None:
        return await self.session.scalar(self._visible().where(Post.id == post_id))

    async def get_loaded(self, post_id: int) -> Post | None:
        stmt = self._with_card_data(select(Post).where(Post.id == post_id))
        return await self.session.scalar(
            stmt.execution_options(populate_existing=True)
        )

    async def add(self, post: Post) -> None:
        self.session.add(post)
        await self.session.flush()

    async def delete(self, post: Post) -> None:
        await self.session.delete(post)
        await self.session.flush()

    async def flush(self) -> None:
        await self.session.flush()

    async def get_klev_source(self) -> Source | None:
        return await self.session.scalar(
            select(Source).where(Source.type == SourceType.KLEV.value).limit(1)
        )

    async def attached_file_ids(
        self, file_ids: list[int], *, except_post_id: int | None = None
    ) -> set[int]:
        stmt = select(PostMedia.media_file_id).where(
            PostMedia.media_file_id.in_(file_ids)
        )
        if except_post_id is not None:
            stmt = stmt.where(PostMedia.post_id != except_post_id)
        return set(await self.session.scalars(stmt))

    async def get_for_interaction(self, post_id: int, *, lock: bool = False) -> Post | None:
        stmt = (
            select(Post)
            .where(
                Post.id == post_id,
                Post.status == PostStatus.PUBLISHED.value,
                Post.canonical_post_id.is_(None),
            )
            .options(selectinload(Post.source))
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def engagement(
        self, post_ids: list[int], user_id: int | None
    ) -> dict[int, PostEngagement]:
        if not post_ids:
            return {}
        likes = select(func.count()).where(PostLike.post_id == Post.id).scalar_subquery()
        comments = select(func.count()).where(Comment.post_id == Post.id).scalar_subquery()
        liked = exists().where(PostLike.post_id == Post.id, PostLike.user_id == user_id)
        rows = await self.session.execute(
            select(Post.id, likes, comments, liked).where(Post.id.in_(post_ids))
        )
        return {
            post_id: PostEngagement(likes, comments, liked)
            for post_id, likes, comments, liked in rows
        }

    async def add_like(self, post_id: int, user_id: int) -> None:
        await self.session.execute(
            insert(PostLike).values(post_id=post_id, user_id=user_id).on_conflict_do_nothing()
        )

    async def remove_like(self, post_id: int, user_id: int) -> None:
        await self.session.execute(
            delete(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user_id)
        )

    async def comments(
        self, post_id: int, cursor: int | None, limit: int
    ) -> list[tuple[Comment, User]]:
        stmt = select(Comment, User).join(User, User.id == Comment.author_id).where(
            Comment.post_id == post_id
        )
        if cursor is not None:
            stmt = stmt.where(Comment.id > cursor)
        rows = await self.session.execute(stmt.order_by(Comment.id).limit(limit + 1))
        return [(comment, author) for comment, author in rows]

    async def get_comment(self, post_id: int, comment_id: int) -> Comment | None:
        return await self.session.scalar(
            select(Comment).where(Comment.id == comment_id, Comment.post_id == post_id)
        )

    async def add_comment(self, comment: Comment) -> None:
        self.session.add(comment)
        await self.session.flush()

    async def delete_comment(self, comment: Comment) -> None:
        await self.session.delete(comment)
        await self.session.flush()
