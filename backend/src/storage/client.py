"""Тонкая обёртка над boto3 (S3-совместимое хранилище).

boto3 синхронный, поэтому все вызовы выполняются в thread-pool через
asyncio.to_thread, чтобы не блокировать остальной асинхронный сбор.
"""

import asyncio
from pathlib import Path

import boto3
from botocore.client import Config
from src.storage.exceptions import StorageNotConfiguredError, UploadError
from src.storage.settings import StorageSettings


class StorageClient:
    def __init__(self, settings: StorageSettings):
        self._settings = settings
        self._client = None
        if settings.is_configured:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                region_name=settings.S3_REGION,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                config=Config(s3={"addressing_style": settings.S3_ADDRESSING_STYLE}),
            )

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def _require_client(self):
        if self._client is None:
            raise StorageNotConfiguredError(
                "S3 не настроен: заполните S3_ENDPOINT_URL/S3_BUCKET/ключи в .env"
            )
        return self._client

    async def upload_file(self, local_path: Path, object_key: str, content_type: str) -> None:
        client = self._require_client()
        bucket = self._settings.S3_BUCKET
        try:
            await asyncio.to_thread(
                client.upload_file,
                str(local_path),
                bucket,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )
        except Exception as exc:  # noqa: BLE001 - boto3 raises many exception types
            raise UploadError(f"не удалось загрузить {object_key}: {exc}") from exc

    async def object_exists(self, object_key: str) -> bool:
        client = self._require_client()
        try:
            await asyncio.to_thread(
                client.head_object, Bucket=self._settings.S3_BUCKET, Key=object_key
            )
            return True
        except client.exceptions.ClientError:
            return False

    async def delete_object(self, object_key: str) -> None:
        client = self._require_client()
        await asyncio.to_thread(
            client.delete_object, Bucket=self._settings.S3_BUCKET, Key=object_key
        )

    async def signed_url(self, object_key: str) -> str:
        client = self._require_client()
        return await asyncio.to_thread(
            client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._settings.S3_BUCKET, "Key": object_key},
            ExpiresIn=self._settings.S3_SIGNED_URL_TTL_S,
        )

    def public_url(self, object_key: str) -> str | None:
        if not self._settings.S3_PUBLIC_BASE_URL:
            return None
        return f"{self._settings.S3_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
