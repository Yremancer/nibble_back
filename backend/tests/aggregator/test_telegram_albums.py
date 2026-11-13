
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.aggregator.sources.telegram_collector import TelegramCollector
from telethon.tl.types import Message


def _make_message(msg_id: int, grouped_id: int | None, media_type: str | None, text: str = ""):
    msg = MagicMock(spec=Message)
    msg.id = msg_id
    msg.grouped_id = grouped_id
    msg.message = text
    msg.date = datetime(2026, 11, 13, 1, 0, tzinfo=timezone.utc)
    msg.edit_date = None
    msg.forward = None
    msg.reactions = None
    msg.replies = None

    if media_type == "photo":
        from telethon.tl.types import MessageMediaPhoto

        msg.media = MagicMock(spec=MessageMediaPhoto)
    elif media_type == "video":
        from telethon.tl.types import MessageMediaDocument

        document = MagicMock()
        document.mime_type = "video/mp4"
        media = MagicMock(spec=MessageMediaDocument)
        media.document = document
        msg.media = media
    else:
        msg.media = None

    return msg


def _fake_iter_messages(messages):
    async def gen(*args, **kwargs):
        for m in messages:
            yield m

    return gen


@pytest.mark.asyncio
async def test_album_across_page_boundary_becomes_one_post():
    messages = [
        _make_message(10, grouped_id=777, media_type="photo", text="Отчёт с фото"),
        _make_message(11, grouped_id=777, media_type="video"),
        _make_message(12, grouped_id=777, media_type="photo"),
        _make_message(13, grouped_id=None, media_type=None, text="Отдельный пост"),
    ]

    client = MagicMock()
    client.iter_messages = _fake_iter_messages(messages)

    channel_entity = MagicMock()
    channel_entity.id = 999
    channel_entity.username = "testchannel"
    client.get_entity = AsyncMock(return_value=channel_entity)

    collector = TelegramCollector(client, "testchannel")

    collected_posts = [post async for post in collector.iter_history()]

    assert len(collected_posts) == 2, "альбом из 3 сообщений + одиночный пост = 2 публикации"

    album_post = collected_posts[0]
    assert album_post.external_id == "10", "external_id берётся от первого сообщения альбома по id"
    assert album_post.all_message_ids == [10, 11, 12]
    assert [t for _, t in album_post.media_refs] == ["photo", "video", "photo"], (
        "порядок фото/видео должен сохраняться как в исходном альбоме"
    )

    single_post = collected_posts[1]
    assert single_post.external_id == "13"
    assert single_post.media_refs == []


@pytest.mark.asyncio
async def test_post_without_caption_is_not_lost():
    messages = [_make_message(20, grouped_id=None, media_type="photo", text="")]

    client = MagicMock()
    client.iter_messages = _fake_iter_messages(messages)
    channel_entity = MagicMock()
    channel_entity.id = 1
    channel_entity.username = "ch"
    client.get_entity = AsyncMock(return_value=channel_entity)

    collector = TelegramCollector(client, "ch")
    posts = [post async for post in collector.iter_history()]

    assert len(posts) == 1
    assert posts[0].text == ""
    assert len(posts[0].media_refs) == 1
