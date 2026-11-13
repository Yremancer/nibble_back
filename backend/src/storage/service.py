from datetime import timedelta

from src.storage.client import StorageClient
from src.storage.exceptions import FileNotFoundInStorageError
from src.storage.models import File
from src.storage.policy import CATEGORIES
from src.storage.repository import FileRepository
from src.storage.utils import (
    build_key,
    check_allowed,
    detect_content_type,
)


class FileService:
    def __init__(self, repo: FileRepository, storage: StorageClient):
        self._repo = repo
        self._storage = storage

    async def upload(
        self,
        data: bytes,
        *,
        filename: str,
        category: str,
    ) -> File:

        cat = CATEGORIES[category]

        content_type = detect_content_type(data)
        check_allowed(data, content_type, cat)

        key = build_key(cat, content_type)

        record = await self._repo.add(
            File(
                key=key,
                original_name=filename,
                content_type=content_type,
                size=len(data),
            )
        )

        await self._storage.put(key, data, content_type=content_type)
        return record

    async def download(self, key: str) -> tuple[bytes, File]:
        record = await self._repo.get_by_key(key)
        if record is None:
            raise FileNotFoundInStorageError

        return await self._storage.get(key), record

    async def link(self, key: str, *, expires: timedelta = timedelta(hours=1)) -> str:
        record = await self._repo.get_by_key(key)
        if record is None:
            raise FileNotFoundInStorageError

        return await self._storage.presigned_url(key, expires=expires)

    async def delete(self, key: str) -> None:
        record = await self._repo.get_by_key(key)
        if record is None:
            raise FileNotFoundInStorageError

        await self._repo.delete(record)
        await self._storage.delete(key)

