from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.exceptions import ConflictError
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

    async def delete(self, record: File) -> None:
        try:
            await self._session.delete(record)
            await self._session.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) in ("23001", "23503"):
                raise ConflictError("File is still used by a post or listing") from exc
            raise
