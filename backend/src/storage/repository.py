from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.media import MediaFile


class MediaFileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_sha256(self, sha256: str) -> MediaFile | None:
        result = await self._session.execute(
            select(MediaFile).where(MediaFile.sha256 == sha256)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> MediaFile:
        media_file = MediaFile(**kwargs)
        self._session.add(media_file)
        await self._session.flush()
        return media_file
