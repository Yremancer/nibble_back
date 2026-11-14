from datetime import datetime

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.city.models import City
from src.user.models import Subscription, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def list_all(self) -> list[User]:
        result = await self._session.scalars(select(User).order_by(User.id))
        return list(result)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(
            select(User).where(func.lower(User.email) == email)
        )

    async def city_exists(self, city_id: int) -> bool:
        return await self._session.get(City, city_id) is not None

    async def get_city(self, city_id: int) -> City | None:
        return await self._session.get(City, city_id)

    async def add_follow(self, follower_id: int, followee_id: int) -> None:
        await self._session.execute(
            insert(Subscription)
            .values(follower_id=follower_id, followee_id=followee_id)
            .on_conflict_do_nothing()
        )

    async def remove_follow(self, follower_id: int, followee_id: int) -> None:
        await self._session.execute(
            delete(Subscription).where(
                Subscription.follower_id == follower_id,
                Subscription.followee_id == followee_id,
            )
        )

    async def follow_counts(self, user_id: int) -> tuple[int, int]:
        """(подписчики, подписки)"""
        followers = await self._session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.followee_id == user_id)
        )
        following = await self._session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.follower_id == user_id)
        )
        return followers, following

    async def is_following(self, follower_id: int, followee_id: int) -> bool:
        return (
            await self._session.get(Subscription, (follower_id, followee_id))
            is not None
        )

    async def followed_among(self, viewer_id: int, user_ids: list[int]) -> set[int]:
        result = await self._session.scalars(
            select(Subscription.followee_id).where(
                Subscription.follower_id == viewer_id,
                Subscription.followee_id.in_(user_ids),
            )
        )
        return set(result)

    async def list_followers(
        self, user_id: int, after: tuple[datetime, int] | None, limit: int
    ) -> list[tuple[User, datetime]]:
        return await self._follow_page(
            Subscription.follower_id, Subscription.followee_id, user_id, after, limit
        )

    async def list_following(
        self, user_id: int, after: tuple[datetime, int] | None, limit: int
    ) -> list[tuple[User, datetime]]:
        return await self._follow_page(
            Subscription.followee_id, Subscription.follower_id, user_id, after, limit
        )

    async def _follow_page(
        self,
        user_column,
        owner_column,
        owner_id: int,
        after: tuple[datetime, int] | None,
        limit: int,
    ) -> list[tuple[User, datetime]]:
        stmt = (
            select(User, Subscription.created_at)
            .join(Subscription, user_column == User.id)
            .where(owner_column == owner_id)
        )
        if after is not None:
            stmt = stmt.where(tuple_(Subscription.created_at, User.id) < tuple_(*after))
        stmt = stmt.order_by(Subscription.created_at.desc(), User.id.desc()).limit(
            limit + 1
        )
        return [(user, created_at) for user, created_at in await self._session.execute(stmt)]

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def update(self, user: User, values: dict) -> User:
        for name, value in values.items():
            setattr(user, name, value)
        await self._session.flush()
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()
