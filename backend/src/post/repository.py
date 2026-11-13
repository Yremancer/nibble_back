from datetime import datetime

from sqlalchemy import Select, exists, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.models.media import PostMedia
from src.models.post import Post, PostSpecies, PostStatus, Source, SourceType
from src.post.schemas import FeedQuery
from src.spot.models import Spot
from src.user.models import User


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
        # Дубли (canonical_post_id) и неопубликованные посты в публичную выдачу не попадают.
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
            # Город поста: место, иначе автор, иначе источник. Источник "Клёв" один
            # на все города, поэтому город пользовательского отчёта берём у автора.
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
        """Пост с данными карточки без фильтра видимости; перечитывает уже загруженный объект."""
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
        """Какие из файлов уже прикреплены к постам (кроме указанного)."""
        stmt = select(PostMedia.media_file_id).where(
            PostMedia.media_file_id.in_(file_ids)
        )
        if except_post_id is not None:
            stmt = stmt.where(PostMedia.post_id != except_post_id)
        return set(await self.session.scalars(stmt))
