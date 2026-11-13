
from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.post.models import Post, PostKind, PostSpecies, PostStatus


class PostWriter:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_post(
        self,
        *,
        existing_post_id: int | None,
        source_id: int,
        external_post_id: str,
        original_url: str | None,
        text: str,
        published_at: datetime,
        kind: PostKind,
        status: PostStatus,
        fishing_date: date | None,
        event_date: date | None,
        spot_id: int | None,
        method_id: int | None,
        bait: str | None,
        conditions: str | None,
        tg_reactions_count: int | None,
        tg_comments_count: int | None,
    ) -> Post:
        if existing_post_id is not None:
            post = await self._session.get(Post, existing_post_id)
        else:
            post = await self._session.scalar(select(Post).where(
                Post.source_id == source_id, Post.external_post_id == external_post_id,
            ).with_for_update())

        managed = (post.managed_fields or {}) if post else {}

        if post is None:
            post = Post(
                source_id=source_id,
                external_post_id=external_post_id,
                original_url=original_url,
                text=text,
                published_at=published_at,
                status=status.value,
            )
            self._session.add(post)
        else:
            if "text" not in managed:
                post.text = text
            if "status" not in managed:
                post.status = status.value

        if "kind" not in managed:
            post.kind = kind.value
        if "fishing_date" not in managed:
            post.fishing_date = fishing_date
        if "event_date" not in managed:
            post.event_date = event_date
        if "spot_id" not in managed:
            post.spot_id = spot_id
        if "method_id" not in managed:
            post.method_id = method_id
        if "bait" not in managed:
            post.bait = bait
        if "conditions" not in managed:
            post.conditions = conditions
        if "published_at" not in managed:
            post.published_at = published_at
        if "original_url" not in managed:
            post.original_url = original_url

        if "tg_reactions_count" not in managed:
            post.tg_reactions_count = tg_reactions_count
        if "tg_comments_count" not in managed:
            post.tg_comments_count = tg_comments_count

        await self._session.flush()
        return post

    async def set_catches(
        self, post_id: int, catches: list[dict]
    ) -> None:
        existing = await self._session.get(Post, post_id)
        if existing is None or any(key in (existing.managed_fields or {}) for key in ("catches", "species")):
            return
        await self._session.execute(delete(PostSpecies).where(PostSpecies.post_id == post_id))
        self._session.expire(existing, ["catches"])
        for catch in catches:
            self._session.add(
                PostSpecies(
                    post_id=post_id,
                    species_id=catch["species_id"],
                    quantity=catch.get("quantity"),
                    max_weight_g=catch.get("max_weight_g"),
                )
            )
        await self._session.flush()
