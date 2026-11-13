import base64
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from src.aggregator.config import SourcesConfig, TelegramSourceConfig
from src.aggregator.exceptions import DownloadError
from src.aggregator.media import MediaService
from src.aggregator.models import AggRawItem
from src.aggregator.repository import CursorRepository
from src.aggregator.sources.telegram_public import PublicTelegramCollector
from src.aggregator.sources.telegram_sync import sync_telegram_source


def post_html(message_id, *, album=False, date="2026-11-12T10:00:00+00:00", text="Отчёт"):
    token = base64.urlsafe_b64encode(json.dumps({"c": -987654321}).encode()).decode().rstrip("=")
    media = ""
    if album:
        media = f"""
        <a class="tgme_widget_message_photo_wrap grouped_media_wrap"
           href="https://t.me/public_test/{message_id}?single"
           style="background-image:url('https://cdn4.telesco.pe/photo.jpg')"></a>
        <a class="grouped_media_wrap" href="https://t.me/public_test/{message_id + 1}?single">
          <video class="tgme_widget_message_video blured js-message_video_blured" src="https://cdn4.telesco.pe/blur.mp4"></video>
          <video class="tgme_widget_message_video js-message_video" src="https://cdn4.telesco.pe/video.mp4?token=new"></video>
        </a>"""
    return f"""<div class="tgme_widget_message" data-post="public_test/{message_id}" data-view="{token}">
      {media}<div class="tgme_widget_message_text">{text}<br>Вторая строка &amp; текст</div>
      <span class="tgme_reaction">2</span><span class="tgme_reaction">1.2K</span>
      <a class="tgme_widget_message_replies">12 comments</a>
      <a class="tgme_widget_message_date"><time datetime="{date}"></time></a>
    </div>"""


def page_html(*posts, before=None):
    more = f'<a class="tme_messages_more" data-before="{before}"></a>' if before else ""
    return more + "".join(posts)


def public_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_public_parser_keeps_album_order_text_identity_and_counters():
    async with public_client(lambda request: httpx.Response(200, text=page_html(post_html(10, album=True)))) as client:
        collector = PublicTelegramCollector(client, "public_test")
        assert await collector.resolve_channel_id() == 987654321
        posts = [post async for post in collector.iter_history(reverse=True)]
        post = posts[0]
        assert post.text == "Отчёт\nВторая строка & текст"
        assert post.all_message_ids == [10, 11]
        assert post.media_refs == [("tgweb:public_test:10:0", "photo"), ("tgweb:public_test:10:1", "video")]
        assert post.reactions_count == 1202
        assert post.comments_count == 12
        assert post.original_url == "https://t.me/public_test/10"
        assert await collector.media_url(10, 1) == "https://cdn4.telesco.pe/video.mp4?token=new"
        with pytest.raises(DownloadError):
            await collector.media_url(10, 2)


async def test_pagination_yields_oldest_first_without_skipping_new_posts(monkeypatch):
    monkeypatch.setattr("src.aggregator.sources.telegram_public.asyncio.sleep", AsyncMock())
    requests = []

    def respond(request):
        requests.append(str(request.url))
        if request.url.params.get("before") == "10":
            html = page_html(post_html(8), post_html(9))
        else:
            html = page_html(post_html(10), post_html(12), before=10)
        return httpx.Response(200, text=html)

    async with public_client(respond) as client:
        collector = PublicTelegramCollector(client, "public_test")
        await collector.resolve_channel_id()
        posts = [post.external_id async for post in collector.iter_history(min_id=8, reverse=True)]
        assert posts == ["9", "10", "12"]
        assert len(requests) == 2


async def test_initial_sync_uses_date_boundary_and_recheck_is_newest_first(monkeypatch):
    monkeypatch.setattr("src.aggregator.sources.telegram_public.asyncio.sleep", AsyncMock())

    def respond(request):
        if request.url.params.get("before") == "10":
            return httpx.Response(200, text=page_html(
                post_html(8, date="2026-11-01T10:00:00+00:00"), post_html(9),
            ))
        return httpx.Response(200, text=page_html(post_html(10), post_html(12), before=10))

    async with public_client(respond) as client:
        collector = PublicTelegramCollector(client, "public_test")
        cutoff = datetime(2026, 11, 10, tzinfo=timezone.utc)
        assert [p.external_id async for p in collector.iter_history(reverse=True, offset_date=cutoff)] == ["9", "10", "12"]
        assert [p.external_id async for p in collector.iter_history(max_id=10)] == ["9", "8"]


async def test_backfill_walks_older_pages_until_since(monkeypatch):
    monkeypatch.setattr("src.aggregator.sources.telegram_public.asyncio.sleep", AsyncMock())
    pages = {
        None: page_html(post_html(12), before=12),
        "12": page_html(post_html(10), before=10),
        "10": page_html(post_html(8, date="2026-11-01T10:00:00+00:00"), before=8),
    }
    async with public_client(lambda r: httpx.Response(200, text=pages[r.url.params.get("before")])) as client:
        collector = PublicTelegramCollector(client, "public_test", since=datetime(2026, 11, 10, tzinfo=timezone.utc))
        assert [p.external_id async for p in collector.iter_history(reverse=True)] == ["10", "12"]


@pytest.mark.parametrize("html", ["<html>Private channel</html>", '<div class="tgme_widget_message" data-post="public_test/1"></div>'])
async def test_unavailable_preview_fails_explicitly(html):
    async with public_client(lambda r: httpx.Response(200, text=html)) as client:
        with pytest.raises(DownloadError):
            await PublicTelegramCollector(client, "public_test").resolve_channel_id()


@pytest.mark.parametrize("channel", ["-100123", "../other", "name?query=x", "https://t.me/channel"])
def test_public_collector_requires_username(channel):
    with pytest.raises(ValueError):
        PublicTelegramCollector(AsyncMock(), channel)


async def test_media_download_refreshes_public_url_without_telethon():
    async with public_client(lambda r: httpx.Response(200, text=page_html(post_html(10, album=True)))) as client:
        service = MediaService(AsyncMock(), client)
        service.store_from_url = AsyncMock(return_value="stored")
        assert await service.store_from_telegram("tgweb:public_test:10:1") == "stored"
        service.store_from_url.assert_awaited_once_with("https://cdn4.telesco.pe/video.mp4?token=new")


async def test_public_sync_is_idempotent_and_keeps_numeric_channel_identity(session):
    async with public_client(lambda r: httpx.Response(200, text=page_html(post_html(10, album=True), post_html(12)))) as client:
        async def sync():
            return await sync_telegram_source(
                session, client, TelegramSourceConfig(name="public test", channel="public_test"),
                SourcesConfig(), mode="sync", since=None, limit=1,
            )

        assert (await sync())["created"] == 1
        assert (await sync())["created"] == 1
        assert (await sync())["created"] == 0
        items = list(await session.scalars(select(AggRawItem).where(AggRawItem.source_key == "telegram:987654321")))
        assert {item.external_id for item in items} == {"10", "12"}
        assert await CursorRepository(session).get("telegram:987654321", "incremental") == {"last_message_id": 12}
