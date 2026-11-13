from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text
from telethon.tl.types import Message, MessageMediaPhoto, PeerChannel, Photo

from src.aggregator.config import SourcesConfig, TelegramSourceConfig
from src.aggregator.models import AggRawItem
from src.aggregator.repository import CursorRepository, MediaAttachmentRepository
from src.aggregator.sources import telegram_sync
from src.aggregator.sources.telegram_collector import TelegramCollector


def message(message_id, *, text="Отчёт", photo_id=None, grouped_id=None, date=None):
    date = date or datetime.now(timezone.utc)
    media = None
    if photo_id is not None:
        media = MessageMediaPhoto(photo=Photo(
            id=photo_id, access_hash=0, file_reference=b"", date=date, sizes=[], dc_id=1,
        ))
    return Message(
        id=message_id, peer_id=PeerChannel(987654321), message=text,
        date=date, media=media, grouped_id=grouped_id,
    )


def client_for(messages):
    async def history(channel, *, min_id=0, max_id=0, reverse=False):
        for msg in sorted(messages, key=lambda m: m.id, reverse=not reverse):
            if msg.id > min_id and (not max_id or msg.id < max_id):
                yield msg

    return SimpleNamespace(
        iter_messages=history,
        get_entity=AsyncMock(return_value=SimpleNamespace(id=987654321, username="sync_test")),
    )


async def sync(session, client, **kwargs):
    return await telegram_sync.sync_telegram_source(
        session, client, TelegramSourceConfig(name="test", channel="sync_test"),
        SourcesConfig(), mode="sync", since=None, limit=kwargs.get("limit"),
    )


@pytest.mark.asyncio
async def test_small_limit_drains_history_without_splitting_album(session):
    messages = [
        message(1), message(2, photo_id=20, grouped_id=100),
        message(3, photo_id=30, grouped_id=100), message(4), message(5),
    ]
    client = client_for(messages)
    for _ in range(3):
        await sync(session, client, limit=2)

    items = list((await session.scalars(select(AggRawItem).where(
        AggRawItem.source_key == "telegram:987654321",
    ))).all())
    assert {item.external_id for item in items} == {"1", "2", "4", "5"}
    album = next(item for item in items if item.external_id == "2")
    attachments = await MediaAttachmentRepository(session).all_for_item(album.id)
    assert [a.source_ref for a in attachments] == ["sync_test:2:20", "sync_test:3:30"]
    assert await CursorRepository(session).get("telegram:987654321", "incremental") == {
        "last_message_id": 5,
    }


@pytest.mark.asyncio
async def test_initial_sync_starts_with_recent_posts_and_backfill_uses_separate_cursor(session):
    cutoff = datetime(2026, 11, 10, tzinfo=timezone.utc)
    messages = [message(1, date=cutoff - timedelta(days=30)), message(2, date=cutoff + timedelta(days=1))]
    client = client_for(messages)
    history = client.iter_messages
    offsets = []

    async def filtered(channel, *, min_id=0, max_id=0, reverse=False, offset_date=None):
        offsets.append(offset_date)
        async for item in history(channel, min_id=min_id, max_id=max_id, reverse=reverse):
            if offset_date is None or item.date > offset_date:
                yield item

    client.iter_messages = filtered
    cfg = TelegramSourceConfig(name="test", channel="sync_test")
    await telegram_sync.sync_telegram_source(session, client, cfg, SourcesConfig(), mode="sync", since=cutoff, limit=2)
    assert list(await session.scalars(select(AggRawItem.external_id).where(AggRawItem.source_key == "telegram:987654321"))) == ["2"]
    assert offsets == [cutoff]
    await telegram_sync.sync_telegram_source(session, client, cfg, SourcesConfig(), mode="backfill", since=None, limit=2)
    assert set(await session.scalars(select(AggRawItem.external_id).where(AggRawItem.source_key == "telegram:987654321"))) == {"1", "2"}
    repo = CursorRepository(session)
    assert (await repo.get("telegram:987654321", "incremental"))["last_message_id"] == 2
    assert (await repo.get("telegram:987654321", "backfill"))["last_message_id"] == 2


@pytest.mark.asyncio
async def test_failed_record_rolls_back_and_blocks_cursor_but_not_later_records(session, monkeypatch):
    original = telegram_sync.ingest_telegram_post

    async def fail_second(session, **kwargs):
        result = await original(session, **kwargs)
        if kwargs["external_id"] == "2":
            await session.execute(text("SELECT 1 / 0"))
        return result

    client = client_for([message(1), message(2), message(3)])
    monkeypatch.setattr(telegram_sync, "ingest_telegram_post", fail_second)
    stats = await sync(session, client)
    assert stats["errors"] == 1
    cursor_repo = CursorRepository(session)
    assert (await cursor_repo.get("telegram:987654321", "incremental"))["last_message_id"] == 1
    assert set(await session.scalars(select(AggRawItem.external_id).where(
        AggRawItem.source_key == "telegram:987654321",
    ))) == {"1", "3"}

    monkeypatch.setattr(telegram_sync, "ingest_telegram_post", original)
    await sync(session, client)
    assert (await cursor_repo.get("telegram:987654321", "incremental"))["last_message_id"] == 3
    assert set(await session.scalars(select(AggRawItem.external_id).where(
        AggRawItem.source_key == "telegram:987654321",
    ))) == {"1", "2", "3"}


@pytest.mark.asyncio
async def test_recheck_updates_text_and_photo_without_changing_identity(session):
    messages = [
        message(1, text="старое", date=datetime.now(timezone.utc) - timedelta(hours=73)),
        message(2, photo_id=20),
    ]
    client = client_for(messages)
    await sync(session, client)
    item = await session.scalar(select(AggRawItem).where(
        AggRawItem.source_key == "telegram:987654321", AggRawItem.external_id == "2",
    ))
    item_id, initial_hash = item.id, item.content_hash
    messages[0].message = "вне окна"
    messages[1] = message(2, photo_id=21)
    stats = await sync(session, client, limit=1)
    assert stats["updated"] == 1
    assert item.id == item_id
    assert item.content_hash == initial_hash
    attachments = await MediaAttachmentRepository(session).all_for_item(item_id)
    assert attachments[0].source_ref == "sync_test:2:21"
    messages[1].message = "ОТРЕДАКТИРОВАНО"
    await sync(session, client, limit=1)
    assert item.id == item_id
    assert item.raw_payload["text"] == "ОТРЕДАКТИРОВАНО"
    old = await session.scalar(select(AggRawItem).where(
        AggRawItem.source_key == "telegram:987654321", AggRawItem.external_id == "1",
    ))
    assert old.raw_payload["text"] == "старое"


@pytest.mark.asyncio
async def test_bad_collected_record_does_not_stop_channel(session, monkeypatch):
    original = TelegramCollector._build_collected_post

    async def fail_second(self, messages):
        if messages[0].id == 2:
            raise ValueError("bad record")
        return await original(self, messages)

    monkeypatch.setattr(TelegramCollector, "_build_collected_post", fail_second)
    stats = await sync(session, client_for([message(1), message(2), message(3)]))
    assert stats["errors"] == 1
    assert set(await session.scalars(select(AggRawItem.external_id).where(
        AggRawItem.source_key == "telegram:987654321",
    ))) == {"1", "3"}
    assert (await CursorRepository(session).get("telegram:987654321", "incremental"))["last_message_id"] == 1


@pytest.mark.asyncio
async def test_one_failed_channel_does_not_roll_back_other_channels(monkeypatch):
    import telethon
    from src.aggregator import commands

    client = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock(), is_user_authorized=AsyncMock(return_value=True))
    monkeypatch.setattr(telethon, "TelegramClient", MagicMock(return_value=client))
    monkeypatch.setattr(commands, "aggregator_settings", SimpleNamespace(
        is_telegram_configured=True, prepare_telegram_session=lambda: "unused",
        TELEGRAM_API_ID=1, TELEGRAM_API_HASH="test", AGG_RECHECK_WINDOW_HOURS=72,
    ))
    monkeypatch.setattr(commands, "load_sources_config", lambda: SourcesConfig(telegram=[
        TelegramSourceConfig(name=name, channel=name) for name in ("first", "bad", "last")
    ]))
    sessions = [AsyncMock() for _ in range(3)]
    factory = MagicMock(side_effect=sessions)
    monkeypatch.setattr(commands, "async_session_maker", factory)
    collect = AsyncMock(side_effect=[{"created": 1}, ValueError("unavailable"), {"created": 1}])
    monkeypatch.setattr(telegram_sync, "sync_telegram_source", collect)
    stats = await commands._run_telegram_sync("sync", None, 1)
    assert stats == {"first": {"created": 1}, "bad": {"errors": 1}, "last": {"created": 1}}
    sessions[0].__aenter__.return_value.commit.assert_awaited_once()
    sessions[1].__aenter__.return_value.commit.assert_not_awaited()
    sessions[2].__aenter__.return_value.commit.assert_awaited_once()
    client.disconnect.assert_awaited_once()
