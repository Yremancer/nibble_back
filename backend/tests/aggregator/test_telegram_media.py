from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text, update
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

from src.aggregator.media import MediaService
from src.aggregator.models import AggProcessingTask, AggRawItem, ProcessingStage
from src.aggregator.pipeline.ingest import ingest_telegram_post
from src.aggregator.pipeline.dedup_stage import process_dedup_tasks
from src.aggregator.pipeline.media_stage import process_media_tasks
from src.aggregator.pipeline.publish_stage import process_publish_tasks
from src.aggregator.repository import (
    ClassificationRepository, MediaAttachmentRepository, RawItemRepository, TaskRepository,
)
from src.llm.settings import llm_settings
from src.models.media import PostMedia
from src.post.models import Post, Source
from src.storage.exceptions import StorageUnavailableError
from src.storage.models import File
from src.storage.repository import FileRepository
from src.storage.service import FileService


@pytest.fixture(autouse=True)
async def isolate_queue(session):
    await session.execute(update(AggProcessingTask).values(
        available_at=datetime.now(timezone.utc) + timedelta(days=365),
    ))


async def ingest(session, source_id, refs, text="Отчёт"):
    item_id, changed, _ = await ingest_telegram_post(
        session, source_key="telegram:media_test", external_id="1",
        raw_payload={
            "source_id": source_id, "external_post_id": "1",
            "published_at": datetime.now(timezone.utc).isoformat(),
        },
        raw_text=text, media_refs=refs, boilerplate_rules=[], parser_version="test",
    )
    if changed:
        version = await RawItemRepository(session).get_current_content_version(item_id)
        repo = ClassificationRepository(session)
        if await repo.get_cached(version.id, llm_settings.DEEPSEEK_MODEL, llm_settings.PROMPT_VERSION) is None:
            await repo.store(
                version.id, model=llm_settings.DEEPSEEK_MODEL, prompt_version=llm_settings.PROMPT_VERSION,
                decision="keep", result={"decision": "keep", "category": "useful_info", "reason": "test"},
                tokens_in=None, tokens_out=None, cost_estimate_usd=None,
            )
    await TaskRepository(session).enqueue(item_id, ProcessingStage.MEDIA)
    return item_id


async def links(session, post_id):
    return list(await session.scalars(
        select(PostMedia).where(PostMedia.post_id == post_id).order_by(PostMedia.sort_order),
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["s3", "database"])
async def test_album_upload_retry_after_publish_replace_and_remove(session, monkeypatch, failure):
    source = Source(type="telegram", name="media_test", external_id="media_test")
    session.add(source)
    await session.flush()
    contents = {1: b"\xff\xd8\xffphoto-a", 2: b"\x00\x00\x00\x18ftypmp42video", 3: b"\xff\xd8\xffphoto-b"}
    messages = {
        1: SimpleNamespace(id=1, media=MessageMediaPhoto(photo=SimpleNamespace(id=20))),
        2: SimpleNamespace(id=2, media=MessageMediaDocument(document=SimpleNamespace(id=30, mime_type="video/mp4"))),
        3: SimpleNamespace(id=3, media=MessageMediaPhoto(photo=SimpleNamespace(id=40))),
    }

    async def download(message, *, file):
        Path(file).write_bytes(contents[message.id])
        return file

    telegram = SimpleNamespace(
        is_connected=MagicMock(return_value=False), connect=AsyncMock(),
        is_user_authorized=AsyncMock(return_value=True),
        get_messages=AsyncMock(side_effect=lambda channel, ids: messages[ids]),
        download_media=AsyncMock(side_effect=download),
    )
    objects = {}
    fail_video = True

    async def put(key, data, *, content_type):
        nonlocal fail_video
        if content_type == "video/mp4" and fail_video and failure == "s3":
            fail_video = False
            raise StorageUnavailableError
        objects[key] = data

    original = MediaAttachmentRepository.mark_uploaded

    async def mark_uploaded(self, attachment, media_file_id):
        nonlocal fail_video
        await original(self, attachment, media_file_id)
        if attachment.attachment_index == 1 and fail_video and failure == "database":
            fail_video = False
            await session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(MediaAttachmentRepository, "mark_uploaded", mark_uploaded)
    storage = SimpleNamespace(put=AsyncMock(side_effect=put), get=AsyncMock(side_effect=lambda key: objects[key]))
    files = FileService(FileRepository(session), storage)
    service = MediaService(files, AsyncMock(), telegram)
    refs = [("media_test:1:20", "photo"), ("media_test:2:30", "video"), ("media_test:3:40", "photo")]
    item_id = await ingest(session, source.id, refs)
    assert await process_media_tasks(session, service, 10) == {"done": 0, "failed": 1}
    await process_dedup_tasks(session, 10)
    assert await process_publish_tasks(session, 10) == {"done": 1, "failed": 0}
    item = await session.get(AggRawItem, item_id)
    post_id = item.post_id
    assert [link.sort_order for link in await links(session, post_id)] == [0, 2]
    attachments = await MediaAttachmentRepository(session).all_for_item(item_id)
    assert [a.download_state for a in attachments] == ["uploaded", "failed", "uploaded"]

    task = await session.scalar(select(AggProcessingTask).where(
        AggProcessingTask.raw_item_id == item_id, AggProcessingTask.stage == "media",
    ))
    task.available_at = datetime.now(timezone.utc)
    await session.flush()
    assert await process_media_tasks(session, service, 10) == {"done": 1, "failed": 0}
    await process_dedup_tasks(session, 10)
    assert await process_publish_tasks(session, 10) == {"done": 1, "failed": 0}
    current_links = await links(session, post_id)
    assert [link.type for link in current_links] == ["photo", "video", "photo"]
    assert telegram.download_media.await_count == 4
    for link, expected in zip(current_links, contents.values()):
        stored = await session.get(File, link.media_file_id)
        data, _ = await files.download(stored.key)
        assert data == expected

    old_file_id = current_links[0].media_file_id
    version_id = (await RawItemRepository(session).get_current_content_version(item_id)).id
    contents[1] = b"\xff\xd8\xffreplacement"
    messages[1].media.photo.id = 21
    assert await ingest(session, source.id, [("media_test:1:21", "photo"), refs[1]]) == item_id
    assert (await RawItemRepository(session).get_current_content_version(item_id)).id == version_id
    attachments = await MediaAttachmentRepository(session).all_for_item(item_id)
    assert [a.download_state for a in attachments] == ["pending", "uploaded"]
    assert await process_media_tasks(session, service, 10) == {"done": 1, "failed": 0}
    await process_dedup_tasks(session, 10)
    assert await process_publish_tasks(session, 10) == {"done": 1, "failed": 0}
    current_links = await links(session, post_id)
    assert len(current_links) == 2
    assert current_links[0].media_file_id != old_file_id
    assert item.post_id == post_id

    await ingest(session, source.id, [], text="Изменённый текст без фото")
    await process_media_tasks(session, service, 10)
    await process_dedup_tasks(session, 10)
    assert await process_publish_tasks(session, 10) == {"done": 1, "failed": 0}
    assert await links(session, post_id) == []
    assert (await session.get(Post, post_id)).text == "Изменённый текст без фото"


@pytest.mark.asyncio
async def test_http_attachments_keep_http_loader(session):
    source = Source(type="telegram", name="http_test", external_id="http_test")
    session.add(source)
    await session.flush()
    await ingest(session, source.id, [("https://example.org/photo.jpg", "photo")])
    stored = File(key="image/http-test.jpg", original_name="test", content_type="image/jpeg", size=4)
    session.add(stored)
    await session.flush()
    service = SimpleNamespace(store_from_url=AsyncMock(return_value=stored), store_from_telegram=AsyncMock())
    assert await process_media_tasks(session, service, 10) == {"done": 1, "failed": 0}
    service.store_from_url.assert_awaited_once_with("https://example.org/photo.jpg")
    service.store_from_telegram.assert_not_awaited()
