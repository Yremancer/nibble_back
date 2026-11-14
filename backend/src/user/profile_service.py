from src.post.repository import PostRepository
from src.storage.images import ImageService
from src.user.exceptions import CannotFollowSelfError, UserNotFoundError
from src.user.models import User
from src.user.repository import UserRepository
from src.user.schemas import CityRef, ProfileOut, UserBrief, UserPage
from src.utils import cursor as cursors


class ProfileService:
    def __init__(
        self, users: UserRepository, posts: PostRepository, images: ImageService
    ) -> None:
        self.users = users
        self.posts = posts
        self.images = images

    async def get_profile(self, user_id: int, viewer: User | None) -> ProfileOut:
        user = await self._require_user(user_id)
        city = await self.users.get_city(user.city_id)
        followers, following = await self.users.follow_counts(user.id)
        avatars = await self.images.links([user.avatar_url])
        return ProfileOut(
            id=user.id,
            display_name=user.display_name,
            avatar_url=avatars.get(user.avatar_url, user.avatar_url),
            bio=user.bio,
            city=CityRef(id=city.id, name=city.name),
            created_at=user.created_at,
            posts_count=await self.posts.count_by_author(user.id),
            followers_count=followers,
            following_count=following,
            is_following=viewer is not None
            and await self.users.is_following(viewer.id, user.id),
            is_me=viewer is not None and viewer.id == user.id,
        )

    async def follow(self, user_id: int, actor: User) -> None:
        if user_id == actor.id:
            raise CannotFollowSelfError
        await self._require_user(user_id)
        await self.users.add_follow(actor.id, user_id)

    async def unfollow(self, user_id: int, actor: User) -> None:
        await self._require_user(user_id)
        await self.users.remove_follow(actor.id, user_id)

    async def followers(
        self, user_id: int, viewer: User | None, cursor: str | None, limit: int
    ) -> UserPage:
        await self._require_user(user_id)
        after = cursors.decode(cursor) if cursor else None
        rows = await self.users.list_followers(user_id, after, limit)
        return await self._page(rows, viewer, limit)

    async def following(
        self, user_id: int, viewer: User | None, cursor: str | None, limit: int
    ) -> UserPage:
        await self._require_user(user_id)
        after = cursors.decode(cursor) if cursor else None
        rows = await self.users.list_following(user_id, after, limit)
        return await self._page(rows, viewer, limit)

    async def _page(self, rows, viewer: User | None, limit: int) -> UserPage:
        page = rows[:limit]
        followed = (
            await self.users.followed_among(viewer.id, [user.id for user, _ in page])
            if viewer and page
            else set()
        )
        last_user, last_at = page[-1] if page else (None, None)
        avatars = await self.images.links(user.avatar_url for user, _ in page)
        return UserPage(
            items=[
                UserBrief(
                    id=user.id,
                    display_name=user.display_name,
                    avatar_url=avatars.get(user.avatar_url, user.avatar_url),
                    is_following=user.id in followed,
                )
                for user, _ in page
            ],
            next_cursor=cursors.encode(last_at, last_user.id)
            if len(rows) > limit
            else None,
        )

    async def _require_user(self, user_id: int) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(id=user_id)
        return user
