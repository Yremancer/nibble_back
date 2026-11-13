import asyncio
import base64
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from src.city.repository import CityRepository
from src.models.media import MediaType, PostMedia
from src.post.models import Comment, Post, PostKind, PostSpecies, PostStatus, SourceType
from src.post.exceptions import (
    CommentForbiddenError,
    CommentNotFoundError,
    ImportedPostLikeError,
    InvalidCursorError,
    InvalidPostError,
    KlevSourceMissingError,
    PostForbiddenError,
    PostNotFoundError,
)
from src.post.repository import PostEngagement, PostRepository
from src.post.schemas import (
    AuthorOut,
    CatchIn,
    CatchOut,
    CommentCreate,
    CommentOut,
    CommentPage,
    FeedQuery,
    MediaOut,
    MethodRef,
    PostCreate,
    PostOut,
    PostPage,
    PostUpdate,
    SourceOut,
    SpotRef,
)
from src.species.repository import SpeciesRepository
from src.spot.repository import SpotRepository
from src.storage.client import StorageClient
from src.storage.exceptions import StorageUnavailableError
from src.storage.models import File
from src.storage.repository import FileRepository
from src.user.models import User, UserRole

logger = logging.getLogger(__name__)

SCALAR_FIELDS = (
    "text",
    "bait",
    "conditions",
    "fishing_date",
    "spot_id",
    "method_id",
    "show_spot",
    "show_date",
)


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


def _media_type(file: File) -> str:
    kind = MediaType.PHOTO if file.content_type.startswith("image/") else MediaType.VIDEO
    return kind.value


class PostService:
    def __init__(
        self,
        repo: PostRepository,
        spots: SpotRepository,
        species: SpeciesRepository,
        files: FileRepository,
        cities: CityRepository,
        storage: StorageClient,
    ) -> None:
        self.repo = repo
        self.spots = spots
        self.species = species
        self.files = files
        self.cities = cities
        self.storage = storage

    async def get_feed(self, query: FeedQuery, viewer: User | None = None) -> PostPage:
        after = decode_cursor(query.cursor) if query.cursor else None
        posts = await self.repo.feed(query, after)
        page, has_more = posts[: query.limit], len(posts) > query.limit
        engagement = await self.repo.engagement(
            [post.id for post in page], viewer.id if viewer else None
        )
        return PostPage(
            items=await asyncio.gather(
                *(
                    self._card(p, viewer, engagement.get(p.id, PostEngagement(0, 0, False)))
                    for p in page
                )
            ),
            next_cursor=encode_cursor(page[-1]) if has_more else None,
        )

    async def get_post(self, post_id: int, viewer: User | None = None) -> PostOut:
        post = await self.repo.get_visible(post_id)
        if post is None:
            raise PostNotFoundError(id=post_id)
        return await self._card(post, viewer)

    async def like(self, post_id: int, user: User) -> None:
        post = await self._interaction_post(post_id)
        if post.source.type != SourceType.KLEV:
            raise ImportedPostLikeError
        await self.repo.add_like(post_id, user.id)

    async def unlike(self, post_id: int, user: User) -> None:
        await self._interaction_post(post_id)
        await self.repo.remove_like(post_id, user.id)

    async def get_comments(
        self, post_id: int, cursor: int | None, limit: int
    ) -> CommentPage:
        if not 1 <= limit <= 100:
            raise InvalidPostError("limit must be between 1 and 100")
        if await self.repo.get_for_interaction(post_id) is None:
            raise PostNotFoundError(id=post_id)
        rows = await self.repo.comments(post_id, cursor, limit)
        return CommentPage(
            items=[self._comment(comment, author) for comment, author in rows[:limit]],
            next_cursor=rows[limit - 1][0].id if len(rows) > limit else None,
        )

    async def create_comment(
        self, post_id: int, data: CommentCreate, user: User
    ) -> CommentOut:
        await self._interaction_post(post_id)
        if data.parent_id is not None:
            if await self.repo.get_comment(post_id, data.parent_id) is None:
                raise CommentNotFoundError(id=data.parent_id)
        comment = Comment(
            post_id=post_id, author_id=user.id, parent_id=data.parent_id, text=data.text
        )
        await self.repo.add_comment(comment)
        return self._comment(comment, user)

    async def delete_comment(self, post_id: int, comment_id: int, user: User) -> None:
        await self._interaction_post(post_id)
        comment = await self.repo.get_comment(post_id, comment_id)
        if comment is None:
            raise CommentNotFoundError(id=comment_id)
        if comment.author_id != user.id and user.role not in (
            UserRole.MODERATOR, UserRole.ADMIN
        ):
            raise CommentForbiddenError
        await self.repo.delete_comment(comment)

    async def _interaction_post(self, post_id: int) -> Post:
        post = await self.repo.get_for_interaction(post_id, lock=True)
        if post is None:
            raise PostNotFoundError(id=post_id)
        return post

    @staticmethod
    def _comment(comment: Comment, author: User) -> CommentOut:
        return CommentOut(
            id=comment.id,
            post_id=comment.post_id,
            parent_id=comment.parent_id,
            text=comment.text,
            author=AuthorOut(
                id=author.id, display_name=author.display_name, avatar_url=author.avatar_url
            ),
            created_at=comment.created_at,
        )

    async def create(self, data: PostCreate, user: User) -> PostOut:
        await self._check_fishing_date(data.fishing_date, user)
        await self._check_refs(
            data.spot_id, data.method_id, [c.species_id for c in data.species]
        )
        files = await self._load_files(data.media)
        source = await self.repo.get_klev_source()
        if source is None:
            raise KlevSourceMissingError
        post = Post(
            source_id=source.id,
            author_id=user.id,
            kind=PostKind.FISHING_REPORT.value,
            status=PostStatus.PUBLISHED.value,
            text=data.text,
            spot_id=data.spot_id,
            method_id=data.method_id,
            bait=data.bait,
            conditions=data.conditions,
            fishing_date=data.fishing_date,
            show_spot=data.show_spot,
            show_date=data.show_date,
            media=[
                PostMedia(media_file_id=f.id, type=_media_type(f), sort_order=i)
                for i, f in enumerate(files)
            ],
            catches=[self._catch(c) for c in data.species],
        )
        await self.repo.add(post)
        return await self._card(await self._reload(post.id), viewer=user)

    async def update(self, post_id: int, data: PostUpdate, user: User) -> PostOut:
        post = await self._own_post(post_id, user)
        sent = data.model_fields_set
        if "fishing_date" in sent:
            await self._check_fishing_date(data.fishing_date, user)
        await self._check_refs(
            data.spot_id if "spot_id" in sent else None,
            data.method_id if "method_id" in sent else None,
            [c.species_id for c in data.species] if data.species else [],
        )
        for field in SCALAR_FIELDS:
            if field in sent:
                setattr(post, field, getattr(data, field))
        removed: list[File] = []
        if data.media is not None:
            removed = await self._replace_media(post, data.media)
        if data.species is not None:
            self._replace_catches(post, data.species)
        await self.repo.flush()
        await self._drop_files(removed)
        return await self._card(await self._reload(post.id), viewer=user)

    async def delete(self, post_id: int, user: User) -> None:
        post = await self._own_post(post_id, user)
        files = [m.media_file for m in post.media]
        await self.repo.delete(post)
        await self._drop_files(files)

    async def _own_post(self, post_id: int, user: User) -> Post:
        post = await self.repo.get_loaded(post_id)
        if post is None or post.status != PostStatus.PUBLISHED.value:
            raise PostNotFoundError(id=post_id)
        if post.author_id != user.id:
            raise PostForbiddenError
        return post

    async def _reload(self, post_id: int) -> Post:
        post = await self.repo.get_loaded(post_id)
        assert post is not None
        return post

    async def _check_fishing_date(self, fishing_date, user: User) -> None:
        if fishing_date is None:
            return
        city = await self.cities.get(user.city_id)
        today = datetime.now(ZoneInfo(city.timezone) if city else None).date()
        if fishing_date > today:
            raise InvalidPostError("fishing_date must not be in the future")

    async def _check_refs(
        self, spot_id: int | None, method_id: int | None, species_ids: list[int]
    ) -> None:
        if spot_id is not None and await self.spots.get_active(spot_id) is None:
            raise InvalidPostError(f"Spot not found (id={spot_id})")
        if method_id is not None and not await self.species.method_exists(method_id):
            raise InvalidPostError(f"Fishing method not found (id={method_id})")
        if species_ids:
            missing = set(species_ids) - await self.species.existing_ids(species_ids)
            if missing:
                raise InvalidPostError(f"Species not found: {sorted(missing)}")

    async def _load_files(
        self, keys: list[str], *, except_post_id: int | None = None
    ) -> list[File]:
        by_key = {f.key: f for f in await self.files.get_by_keys(keys)}
        missing = [k for k in keys if k not in by_key]
        if missing:
            raise InvalidPostError(f"Files not found: {missing}")
        files = [by_key[k] for k in keys]
        busy = await self.repo.attached_file_ids(
            [f.id for f in files], except_post_id=except_post_id
        )
        if busy:
            raise InvalidPostError("Files are already attached to another post")
        return files

    @staticmethod
    def _catch(data: CatchIn) -> PostSpecies:
        return PostSpecies(
            species_id=data.species_id,
            quantity=data.quantity,
            max_weight_g=data.max_weight_g,
        )

    async def _replace_media(self, post: Post, keys: list[str]) -> list[File]:
        files = await self._load_files(keys, except_post_id=post.id)
        current = {m.media_file_id: m for m in post.media}
        media = []
        for index, file in enumerate(files):
            item = current.pop(file.id, None) or PostMedia(
                media_file_id=file.id, type=_media_type(file)
            )
            item.sort_order = index
            media.append(item)
        removed = [m.media_file for m in current.values()]
        post.media = media
        return removed

    def _replace_catches(self, post: Post, catches: list[CatchIn]) -> None:
        current = {c.species_id: c for c in post.catches}
        items = []
        for data in catches:
            item = current.pop(data.species_id, None) or self._catch(data)
            item.quantity = data.quantity
            item.max_weight_g = data.max_weight_g
            items.append(item)
        post.catches = items

    async def _drop_files(self, files: list[File]) -> None:
        for file in files:
            await self.files.delete(file)
        for file in files:
            try:
                await self.storage.delete(file.key)
            except StorageUnavailableError:
                logger.warning("Failed to delete %s from storage", file.key)

    async def _card(
        self,
        post: Post,
        viewer: User | None = None,
        engagement: PostEngagement | None = None,
    ) -> PostOut:
        if engagement is None:
            stats = await self.repo.engagement([post.id], viewer.id if viewer else None)
            engagement = stats.get(post.id, PostEngagement(0, 0, False))
        urls = await asyncio.gather(
            *(self.storage.presigned_url(m.media_file.key) for m in post.media)
        )
        own = viewer is not None and post.author_id == viewer.id
        return PostOut(
            id=post.id,
            kind=post.kind,
            text=post.text,
            bait=post.bait,
            conditions=post.conditions,
            published_at=post.published_at,
            fishing_date=post.fishing_date if post.show_date or own else None,
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
            if post.spot and (post.show_spot or own)
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
            likes_count=engagement.likes_count,
            comments_count=engagement.comments_count,
            liked_by_me=engagement.liked_by_me,
            tg_reactions_count=post.tg_reactions_count,
            tg_comments_count=post.tg_comments_count,
            original_url=post.original_url,
        )
