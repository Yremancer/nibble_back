from datetime import timedelta

from botocore.exceptions import BotoCoreError, ClientError
from src.storage.exceptions import (
    FileNotFoundInStorageError,
    StorageUnavailableError,
)


class StorageClient:
    def __init__(self, s3, bucket: str):
        self._s3 = s3
        self._bucket = bucket

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            await self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as e:
            raise StorageUnavailableError from e

    async def get(self, key: str) -> bytes:
        try:
            resp = await self._s3.get_object(Bucket=self._bucket, Key=key)
            async with resp["Body"] as body:
                return await body.read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                raise FileNotFoundInStorageError from e
            raise StorageUnavailableError from e
        except BotoCoreError as e:
            raise StorageUnavailableError from e

    async def delete(self, key: str) -> None:
        try:
            await self._s3.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as e:
            raise StorageUnavailableError from e

    async def presigned_url(
        self, key: str, *, expires: timedelta = timedelta(hours=1)
    ) -> str:
        try:
            return await self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=int(expires.total_seconds()),
            )
        except (BotoCoreError, ClientError) as e:
            raise StorageUnavailableError from e
