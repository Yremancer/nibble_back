import asyncio
import hashlib
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from telethon import TelegramClient
from src.aggregator.exceptions import DownloadError
from src.aggregator.safe_fetch import download_to_file
from src.aggregator.sources.telegram_collector import TelegramCollector
from src.storage.exceptions import FileTooLargeError
from src.storage.mime import EXTENSIONS
from src.storage.models import File
from src.storage.policy import CATEGORIES
from src.storage.service import FileService
from src.storage.utils import detect_content_type

MAX_FILE_BYTES = max(category.max_bytes for category in CATEGORIES.values())


def _read_limited(path: Path) -> bytes:
    with path.open("rb") as source:
        return source.read(MAX_FILE_BYTES + 1)


class MediaService:
    def __init__(
        self, files: FileService, http: httpx.AsyncClient,
        telegram: TelegramClient | None = None,
    ):
        self._files = files
        self._http = http
        self._telegram = telegram

    async def store_from_telegram(self, source_ref: str) -> File:
        if self._telegram is None:
            raise DownloadError("Telegram client is not configured")
        if not self._telegram.is_connected():
            await self._telegram.connect()
        if not await self._telegram.is_user_authorized():
            raise DownloadError("Telegram session is not authorized")
        channel = source_ref.split(":", 1)[0]
        collector = TelegramCollector(self._telegram, channel)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "download"
            if not await collector.download_media(source_ref, str(path)):
                raise DownloadError("Telegram attachment is unavailable or changed")
            return await self.store_from_local_file(path)

    async def store_from_url(self, url: str) -> File:
        filename = unquote(Path(urlsplit(url).path).name) or "media"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "download"
            await download_to_file(self._http, url, path, MAX_FILE_BYTES)
            return await self.store_from_local_file(path, filename=filename)

    async def store_from_local_file(self, path: Path, *, filename: str | None = None) -> File:
        data = await asyncio.to_thread(_read_limited, path)
        if len(data) > MAX_FILE_BYTES:
            raise FileTooLargeError
        content_type = detect_content_type(data)
        category = "image" if content_type.startswith("image/") else "video"
        digest = await asyncio.to_thread(lambda: hashlib.sha256(data).hexdigest())
        return await self._files.upload(
            data,
            filename=filename or path.name,
            category=category,
            key=f"{category}/{digest}{EXTENSIONS[content_type]}",
        )
