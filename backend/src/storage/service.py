"""Сценарии работы с медиафайлами: скачать/принять локальный файл,
определить реальный формат, посчитать sha256, переиспользовать
существующий объект или загрузить новый в S3, построить превью для видео.
"""

import tempfile
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.media import MediaFile, MediaUploadState
from src.storage.client import StorageClient
from src.storage.exceptions import DownloadError
from src.storage.mime import detect_mime, media_type_for_mime
from src.storage.repository import MediaFileRepository
from src.storage.safe_fetch import download_to_file
from src.storage.settings import StorageSettings
from src.storage.utils import (
    build_object_key,
    image_dimensions,
    make_video_preview,
    probe_video,
    sha256_of_file,
)


class MediaService:
    def __init__(
        self,
        session: AsyncSession,
        storage_client: StorageClient,
        settings: StorageSettings,
        http_client: httpx.AsyncClient,
    ):
        self._session = session
        self._client = storage_client
        self._settings = settings
        self._http = http_client
        self._repo = MediaFileRepository(session)

    async def store_from_url(self, url: str) -> MediaFile:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / f"{uuid4().hex}.bin"
            await download_to_file(
                self._http, url, tmp_path, self._settings.S3_MAX_FILE_SIZE_BYTES
            )
            return await self._store_local_file(tmp_path)

    async def store_from_local_file(self, local_path: Path) -> MediaFile:
        size = local_path.stat().st_size
        if size > self._settings.S3_MAX_FILE_SIZE_BYTES:
            raise DownloadError(
                f"файл {local_path} превышает лимит "
                f"{self._settings.S3_MAX_FILE_SIZE_BYTES} байт"
            )
        return await self._store_local_file(local_path)

    async def _store_local_file(self, local_path: Path) -> MediaFile:
        sha256 = sha256_of_file(local_path)

        existing = await self._repo.get_by_sha256(sha256)
        if existing is not None:
            return existing

        mime_type = detect_mime(local_path)
        media_type = media_type_for_mime(mime_type)
        extension = _extension_for_mime(mime_type)
        object_key = build_object_key(sha256, extension)

        width = height = duration_s = None
        preview_key = None

        if media_type == "photo":
            dims = image_dimensions(local_path)
            if dims:
                width, height = dims
        elif media_type == "video":
            probe = await probe_video(local_path)
            if probe:
                width, height, duration_s = (
                    probe.get("width"),
                    probe.get("height"),
                    probe.get("duration_s"),
                )
            preview_path = local_path.with_suffix(".preview.jpg")
            if await make_video_preview(local_path, preview_path):
                preview_sha = sha256_of_file(preview_path)
                preview_key = build_object_key(preview_sha, ".jpg")
                if self._client.is_configured:
                    await self._client.upload_file(preview_path, preview_key, "image/jpeg")
                preview_path.unlink(missing_ok=True)

        upload_state = MediaUploadState.PENDING
        if self._client.is_configured:
            await self._client.upload_file(local_path, object_key, mime_type)
            upload_state = MediaUploadState.UPLOADED

        return await self._repo.create(
            bucket=self._settings.S3_BUCKET or "",
            object_key=object_key,
            sha256=sha256,
            mime_type=mime_type,
            size_bytes=local_path.stat().st_size,
            width=width,
            height=height,
            duration_s=duration_s,
            preview_object_key=preview_key,
            upload_state=upload_state.value,
        )

    async def public_url_for(self, media_file: MediaFile) -> str:
        public = self._client.public_url(media_file.object_key)
        if public:
            return public
        return await self._client.signed_url(media_file.object_key)


_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}


def _extension_for_mime(mime_type: str) -> str:
    return _EXTENSION_BY_MIME.get(mime_type, "")
