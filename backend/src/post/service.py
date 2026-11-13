import asyncio
import base64
from datetime import datetime

from src.models.post import Post
from src.post.exceptions import InvalidCursorError, PostNotFoundError
from src.post.repository import PostRepository
from src.post.schemas import (
    AuthorOut,
    CatchOut,
    FeedQuery,
    MediaOut,
    MethodRef,
    PostOut,
    PostPage,
    SourceOut,
    SpotRef,
)
from src.storage.client import StorageClient


def encode_cursor(post: Post) -> str:
    raw = f"{post.published_at.isoformat()}|{post.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        published_at, post_id = base64.urlsafe_b64decode(padded).decode().split("|")
        return datetime.fromisoformat(published_at), int(post_id)
    except ValueError as exc:
        raise InvalidCursorError from exc


class PostService:
    def __init__(self, repo: PostRepository, storage: StorageClient) -> None:
        self.repo = repo
        self.storage = storage

    async def get_feed(self, query: FeedQuery) -> PostPage:
        after = decode_cursor(query.cursor) if query.cursor else None
        posts = await self.repo.feed(query, after)
        page, has_more = posts[: query.limit], len(posts) > query.limit
        return PostPage(
            items=await asyncio.gather(*(self._card(p) for p in page)),
            next_cursor=encode_cursor(page[-1]) if has_more else None,
        )

    async def get_post(self, post_id: int) -> PostOut:
        post = await self.repo.get_visible(post_id)
        if post is None:
            raise PostNotFoundError(id=post_id)
        return await self._card(post)

    async def _card(self, post: Post) -> PostOut:
        urls = await asyncio.gather(
            *(self.storage.presigned_url(m.media_file.key) for m in post.media)
        )
        return PostOut(
            id=post.id,
            kind=post.kind,
            text=post.text,
            bait=post.bait,
            conditions=post.conditions,
            published_at=post.published_at,
            # Автор сам решает, раскрывать ли место и дату выезда.
            fishing_date=post.fishing_date if post.show_date else None,
            event_date=post.event_date,
            source=SourceOut(
                id=post.source.id,
                type=post.source.type,
                name=post.source.name,
                url=post.source.url,
            ),
            author=AuthorOut(
                id=post.author.id,
                display_name=post.author.display_name,
                avatar_url=post.author.avatar_url,
            )
            if post.author
            else None,
            spot=SpotRef(id=post.spot.id, name=post.spot.name)
            if post.spot and post.show_spot
            else None,
            method=MethodRef(id=post.method.id, name=post.method.name)
            if post.method
            else None,
            species=[
                CatchOut(
                    id=c.species.id,
                    name=c.species.name,
                    quantity=c.quantity,
                    max_weight_g=c.max_weight_g,
                )
                for c in post.catches
            ],
            media=[
                MediaOut(type=m.type, url=url)
                for m, url in zip(post.media, urls, strict=True)
            ],
            likes_count=post.likes_count,
            comments_count=post.comments_count,
            tg_reactions_count=post.tg_reactions_count,
            tg_comments_count=post.tg_comments_count,
            original_url=post.original_url,
        )
