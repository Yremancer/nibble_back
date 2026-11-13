"""Сценарии 14 и 15: одинаковый файл переиспользуется по sha256, удаление
одной связи не удаляет общий медиафайл, используемый другими постами."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from src.models.media import PostMedia
from src.models.post import Post, Source
from src.aggregator.media import MediaService
from src.storage.client import StorageClient
from src.storage.models import File
from src.storage.exceptions import StorageUnavailableError
from src.storage.repository import FileRepository
from src.storage.service import FileService


@pytest.mark.asyncio
async def test_same_file_content_reuses_media_file(session):
    storage_client = AsyncMock(spec=StorageClient)
    http_client = AsyncMock()

    service = MediaService(FileService(FileRepository(session), storage_client), http_client)

    with tempfile.TemporaryDirectory() as tmp:
        file_a = Path(tmp) / "a.jpg"
        file_b = Path(tmp) / "b.jpg"
        same_content = b"\xff\xd8\xff\xe0" + b"fake-jpeg-bytes" * 10
        file_a.write_bytes(same_content)
        file_b.write_bytes(same_content)

        media_a = await service.store_from_local_file(file_a)
        media_b = await service.store_from_local_file(file_b)

    assert media_a.id == media_b.id, "одинаковое содержимое должно переиспользовать media_file"

    storage_client.put.assert_awaited_once()
    count = await session.execute(select(File).where(File.key == media_a.key))
    assert len(count.scalars().all()) == 1


@pytest.mark.asyncio
async def test_deleting_one_post_media_link_keeps_shared_file(session):
    source = Source(type="telegram", name="test", external_id="1")
    session.add(source)
    await session.flush()

    media_file = File(
        key="image/shared.jpg", original_name="shared.jpg",
        content_type="image/jpeg", size=100,
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

    still_exists = await session.get(File, media_file.id)
    assert still_exists is not None, "удаление одной связи не должно удалять общий файл"

    remaining_links = await session.execute(
        select(PostMedia).where(PostMedia.media_file_id == media_file.id)
    )
    assert len(remaining_links.scalars().all()) == 1

@pytest.mark.asyncio
async def test_failed_upload_does_not_leave_file_metadata(session):
    storage_client = AsyncMock(spec=StorageClient)
    storage_client.put.side_effect = StorageUnavailableError
    service = MediaService(FileService(FileRepository(session), storage_client), AsyncMock())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "failure.jpg"
        path.write_bytes(b"\xff\xd8\xfftest-image")
        with pytest.raises(StorageUnavailableError):
            async with session.begin_nested():
                await service.store_from_local_file(path)
    assert await session.scalar(select(File).where(File.original_name == "failure.jpg")) is None
