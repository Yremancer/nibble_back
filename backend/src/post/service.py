import asyncio
import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.auth.exceptions import AuthenticationError
from src.city.repository import CityRepository
from src.post.exceptions import (
    CommentForbiddenError,
    CommentNotFoundError,
    ImportedPostLikeError,
    InvalidPostError,
    KlevSourceMissingError,
    PostForbiddenError,
    PostNotFoundError,
)
from src.post.models import (
    Comment,
    MediaType,
    Post,
    PostKind,
    PostMedia,
    PostSpecies,
    PostStatus,
    SourceType,
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
    PostAuthorOut,
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
from src.storage.images import ImageService
from src.storage.models import File
from src.storage.repository import FileRepository
from src.user.models import User, UserRole
from src.utils import cursor as cursors

logger = logging.getLogger(__name__)

SCALAR_FIELDS = (
    "text",
    "bait",
    "conditions",
    "spot_id",
    "method_id",
    "show_spot",
    "show_date",
)


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
        self.images = ImageService(files, storage)

    async def get_feed(self, query: FeedQuery, viewer: User | None = None) -> PostPage:
        if query.following and viewer is None:
            raise AuthenticationError
        after = cursors.decode(query.cursor) if query.cursor else None
        posts = await self.repo.feed(query, after, viewer.id if viewer else None)
        page, has_more = posts[: query.limit], len(posts) > query.limit
        viewer_id = viewer.id if viewer else None
        engagement = await self.repo.engagement([post.id for post in page], viewer_id)
        followed = await self._followed_authors(viewer_id, page)
        avatars = await self.images.links(p.author.avatar_url for p in page if p.author)
        return PostPage(
            items=await asyncio.gather(
                *(
                    self._card(
                        p,
                        viewer,
                        engagement.get(p.id, PostEngagement(0, 0, False)),
                        followed,
                        avatars=avatars,
                    )
                    for p in page
                )
            ),
            next_cursor=cursors.encode(page[-1].published_at, page[-1].id)
            if has_more
            else None,
        )

    async def _followed_authors(
        self, viewer_id: int | None, posts: list[Post]
    ) -> set[int]:
        author_ids = {p.author_id for p in posts if p.author_id is not None}
        if viewer_id is None or not author_ids:
            return set()
        return await self.repo.followed_author_ids(viewer_id, list(author_ids))

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
        avatars = await self.images.links(author.avatar_url for _, author in rows[:limit])
        return CommentPage(
            items=[self._comment(comment, author, avatars) for comment, author in rows[:limit]],
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
        return self._comment(comment, user, await self.images.links([user.avatar_url]))

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
    def _comment(comment: Comment, author: User, avatars: dict[str, str]) -> CommentOut:
        if comment.is_hidden:
            return CommentOut(
                id=comment.id,
                post_id=comment.post_id,
                parent_id=comment.parent_id,
                text=None,
                author=None,
                created_at=comment.created_at,
                is_hidden=True,
            )
        return CommentOut(
            id=comment.id,
            post_id=comment.post_id,
            parent_id=comment.parent_id,
            text=comment.text,
            author=AuthorOut(
                id=author.id,
                display_name=author.display_name,
                avatar_url=avatars.get(author.avatar_url, author.avatar_url),
            ),
            created_at=comment.created_at,
            is_hidden=False,
        )

    async def create(self, data: PostCreate, user: User) -> PostOut:
        await self._check_fishing_moment(data.fishing_date, data.fishing_time, user)
        await self._check_refs(
            data.spot_id, data.method_id, [c.species_id for c in data.species]
        )
        files = await self._load_files(data.media, user)
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
            fishing_time=data.fishing_time,
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
        if "fishing_date" in sent or "fishing_time" in sent:
            fishing_date = data.fishing_date if "fishing_date" in sent else post.fishing_date
            fishing_time = data.fishing_time if "fishing_time" in sent else post.fishing_time
            if "fishing_date" in sent and fishing_date is None and "fishing_time" not in sent:
                fishing_time = None  # время без даты не бывает: сбрасываем вместе с датой
            if fishing_time is not None and fishing_date is None:
                raise InvalidPostError("fishing_time requires fishing_date")
            await self._check_fishing_moment(fishing_date, fishing_time, user)
            post.fishing_date, post.fishing_time = fishing_date, fishing_time
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
            removed = await self._replace_media(post, data.media, user)
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

    async def _check_fishing_moment(
        self, fishing_date: date | None, fishing_time: time | None, user: User
    ) -> None:
        if fishing_date is None:
            return
        city = await self.cities.get(user.city_id)
        now = datetime.now(ZoneInfo(city.timezone) if city else None)
        if fishing_date > now.date():
            raise InvalidPostError("fishing_date must not be in the future")
        if (
            fishing_time is not None
            and fishing_date == now.date()
            and fishing_time > now.time()
        ):
            raise InvalidPostError("fishing_time must not be in the future")

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
        self, keys: list[str], user: User, *, except_post_id: int | None = None
    ) -> list[File]:
        by_key = {f.key: f for f in await self.files.get_by_keys(keys)}
        missing = [k for k in keys if k not in by_key]
        if missing:
            raise InvalidPostError(f"Files not found: {missing}")
        files = [by_key[k] for k in keys]
        # Чужой файл прикрепить нельзя, даже если знаешь его key.
        if any(f.uploaded_by != user.id for f in files):
            raise InvalidPostError("You can attach only files you uploaded")
        busy = await self.repo.attached_file_ids(
            [f.id for f in files], except_post_id=except_post_id
        )
        if busy or await self.files.used_as_image([f.key for f in files]):
            raise InvalidPostError("Files are already in use")
        return files

    @staticmethod
    def _catch(data: CatchIn) -> PostSpecies:
        return PostSpecies(
            species_id=data.species_id,
            quantity=data.quantity,
            max_weight_g=data.max_weight_g,
        )

    async def _replace_media(
        self, post: Post, keys: list[str], user: User
    ) -> list[File]:
        files = await self._load_files(keys, user, except_post_id=post.id)
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
        followed: set[int] | None = None,
        reveal: bool = False,
        avatars: dict[str, str] | None = None,
    ) -> PostOut:
        if engagement is None:
            stats = await self.repo.engagement([post.id], viewer.id if viewer else None)
            engagement = stats.get(post.id, PostEngagement(0, 0, False))
        if followed is None:
            followed = await self._followed_authors(viewer.id if viewer else None, [post])
        if avatars is None:
            avatars = await self.images.links([post.author.avatar_url] if post.author else [])
        urls = await asyncio.gather(
            *(self.storage.presigned_url(m.media_file.key) for m in post.media)
        )
        own = reveal or (viewer is not None and post.author_id == viewer.id)
        return PostOut(
            id=post.id,
            kind=post.kind,
            text=post.text,
            bait=post.bait,
            conditions=post.conditions,
            published_at=post.published_at,
            fishing_date=post.fishing_date if post.show_date or own else None,
            fishing_time=post.fishing_time if post.show_date or own else None,
            event_date=post.event_date,
            source=SourceOut(
                id=post.source.id,
                type=post.source.type,
                name=post.source.name,
                url=post.source.url,
            ),
            author=PostAuthorOut(
                id=post.author.id,
                display_name=post.author.display_name,
                avatar_url=avatars.get(post.author.avatar_url, post.author.avatar_url),
                is_following=post.author.id in followed,
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
