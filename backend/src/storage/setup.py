from contextlib import asynccontextmanager

import aioboto3
from botocore.config import Config
from fastapi import FastAPI
from src.settings import settings
from src.storage.client import StorageClient


@asynccontextmanager
async def setup_storage(app: FastAPI):
    session = aioboto3.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
    )

    async with session.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL or None,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    ) as s3:
        app.state.storage = StorageClient(s3, settings.S3_BUCKET)
        yield
