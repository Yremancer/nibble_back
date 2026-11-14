import asyncio
import logging
from collections.abc import Iterable
from typing import TypeVar

from pydantic import BaseModel
from src.storage.client import StorageClient
from src.storage.exceptions import InvalidImageError, StorageUnavailableError
from src.storage.repository import FileRepository
from src.user.models import User

logger = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


class ImageService:

    def __init__(self, files: FileRepository, storage: StorageClient) -> None:
        self.files = files
        self.storage = storage

    async def links(self, values: Iterable[str | None]) -> dict[str, str]:
        keys = {v for v in values if v}
        if not keys:
            return {}
        found = [f.key for f in await self.files.get_by_keys(list(keys))]
        urls = await asyncio.gather(*(self.storage.presigned_url(k) for k in found))
        links = dict(zip(found, urls, strict=True))
        return {v: links.get(v, v) for v in keys}

    async def apply(self, items: list[M], field: str) -> list[M]:
        links = await self.links(getattr(item, field) for item in items)
        return [
            item.model_copy(update={field: links.get(getattr(item, field), getattr(item, field))})
            for item in items
        ]

    async def apply_one(self, item: M, field: str) -> M:
        return (await self.apply([item], field))[0]

    async def claim(self, key: str, actor: User, *, current: str | None = None) -> str:
        if key == current:
            return key
        file = await self.files.get_by_key(key)
        if file is None:
            raise InvalidImageError("File not found")
        if not file.content_type.startswith("image/"):
            raise InvalidImageError("Only images are allowed")
        if file.uploaded_by != actor.id:
            raise InvalidImageError("You can use only files you uploaded")
        if await self.files.is_in_use(file):
            raise InvalidImageError("File is already in use")
        return key

    async def release(self, value: str | None) -> None:
        if not value:
            return
        file = await self.files.get_by_key(value)
        if file is None:
            return
        await self.files.delete(file)
        try:
            await self.storage.delete(value)
        except StorageUnavailableError:
            logger.warning("Failed to delete %s from storage", value)
