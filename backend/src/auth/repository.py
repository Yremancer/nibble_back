from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.geo import City
from src.models.user import User


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

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
