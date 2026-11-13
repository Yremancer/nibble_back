from datetime import datetime

from sqlalchemy import Select, exists, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.models.media import PostMedia
from src.models.post import Post, PostSpecies, PostStatus, Source
from src.models.user import User
from src.post.schemas import FeedQuery
from src.spot.models import Spot


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _visible() -> Select[tuple[Post]]:
        # Дубли (canonical_post_id) и неопубликованные посты в публичную выдачу не попадают.
        return (
            select(Post)
            .join(Source, Source.id == Post.source_id)
            .outerjoin(Spot, Spot.id == Post.spot_id)
            .outerjoin(User, User.id == Post.author_id)
            .where(
                Post.status == PostStatus.PUBLISHED.value,
                Post.canonical_post_id.is_(None),
            )
            .options(
                selectinload(Post.source),
                selectinload(Post.author),
                selectinload(Post.spot),
                selectinload(Post.method),
                selectinload(Post.media).selectinload(PostMedia.media_file),
                selectinload(Post.catches).selectinload(PostSpecies.species),
            )
        )

    async def feed(
        self, query: FeedQuery, after: tuple[datetime, int] | None
    ) -> list[Post]:
        stmt = self._visible()
        if query.city_id is not None:
            # Город поста: место, иначе источник, иначе автор.
            stmt = stmt.where(
                func.coalesce(Spot.city_id, Source.city_id, User.city_id)
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
