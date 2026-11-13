from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.storage.models import File


class FileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, record: File) -> File:
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_by_key(self, key: str) -> File | None:
        return await self._session.scalar(select(File).where(File.key == key))

    async def get_by_keys(self, keys: list[str]) -> list[File]:
        result = await self._session.scalars(select(File).where(File.key.in_(keys)))
        return list(result)

    async def delete(self, record: File) -> None:
        await self._session.delete(record)
        await self._session.flush()
