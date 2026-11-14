from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.post.models import PostMedia
from src.species.models import Species
from src.spot.models import Spot
from src.storage.models import File
from src.user.models import User


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

    async def used_as_image(self, keys: list[str]) -> set[str]:
        """Какие из ключей уже служат аватаром, фото места или картинкой вида."""
        used: set[str] = set()
        for column in (User.avatar_url, Spot.photo_url, Species.image_url):
            used |= set(await self._session.scalars(select(column).where(column.in_(keys))))
        return used

    async def is_in_use(self, file: File) -> bool:
        attached = await self._session.scalar(
            select(PostMedia.id).where(PostMedia.media_file_id == file.id).limit(1)
        )
        return attached is not None or bool(await self.used_as_image([file.key]))
