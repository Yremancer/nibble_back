"""Сценарии 14 и 15: одинаковый файл переиспользуется по sha256, удаление
одной связи не удаляет общий медиафайл, используемый другими постами."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from src.models.media import MediaFile, PostMedia
from src.models.post import Post, Source
from src.storage.client import StorageClient
from src.storage.service import MediaService
from src.storage.settings import StorageSettings


@pytest.mark.asyncio
async def test_same_file_content_reuses_media_file(session):
    settings = StorageSettings(S3_MAX_FILE_SIZE_BYTES=10_000_000)
    storage_client = StorageClient(settings)  # не настроен -> upload_state=pending, без реального S3
    http_client = AsyncMock()

    service = MediaService(session, storage_client, settings, http_client)

    with tempfile.TemporaryDirectory() as tmp:
        file_a = Path(tmp) / "a.jpg"
        file_b = Path(tmp) / "b.jpg"
        same_content = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes" * 10
        file_a.write_bytes(same_content)
        file_b.write_bytes(same_content)

        media_a = await service.store_from_local_file(file_a)
        media_b = await service.store_from_local_file(file_b)

    assert media_a.id == media_b.id, "одинаковое содержимое должно переиспользовать media_file"

    count = await session.execute(select(MediaFile).where(MediaFile.sha256 == media_a.sha256))
    assert len(count.scalars().all()) == 1


@pytest.mark.asyncio
async def test_deleting_one_post_media_link_keeps_shared_file(session):
    source = Source(type="telegram", name="test", external_id="1")
    session.add(source)
    await session.flush()

    media_file = MediaFile(
        bucket="test", object_key="media/ab/cd/abcd.jpg", sha256="abcd" * 16,
        mime_type="image/jpeg", size_bytes=100, upload_state="uploaded",
    )
    session.add(media_file)
    await session.flush()

    post1 = Post(source_id=source.id, external_post_id="p1", text="t1")
    post2 = Post(source_id=source.id, external_post_id="p2", text="t2")
    session.add_all([post1, post2])
    await session.flush()

    link1 = PostMedia(post_id=post1.id, media_file_id=media_file.id, type="photo", sort_order=0)
    link2 = PostMedia(post_id=post2.id, media_file_id=media_file.id, type="photo", sort_order=0)
    session.add_all([link1, link2])
    await session.flush()

    await session.delete(link1)
    await session.flush()

    still_exists = await session.get(MediaFile, media_file.id)
    assert still_exists is not None, "удаление одной связи не должно удалять общий файл"

    remaining_links = await session.execute(
        select(PostMedia).where(PostMedia.media_file_id == media_file.id)
    )
    assert len(remaining_links.scalars().all()) == 1
