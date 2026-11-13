from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.city.models import City
from src.user.models import User


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
