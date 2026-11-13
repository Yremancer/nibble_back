import asyncio
import base64
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from selectolax.parser import HTMLParser

from src.aggregator.exceptions import DownloadError
from src.aggregator.schemas import TelegramMediaPreview, TelegramPostPreview
from src.aggregator.sources.telegram_collector import CollectedPost


class PublicTelegramCollector:
    def __init__(self, client: httpx.AsyncClient, channel: str, *, since: datetime | None = None):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", channel):
            raise ValueError("Публичное чтение Telegram требует username открытого канала")
        self._client = client
        self._channel = channel
        self._since = since
        self._latest: HTMLParser | None = None
        self._media_urls: dict[str, list[tuple[str, str]]] = {}

    async def _page(self, *, before: int = 0, message_id: int = 0) -> HTMLParser:
        url = f"https://t.me/s/{self._channel}"
        if message_id:
            url += f"/{message_id}"
        response = await self._client.get(url, params={"before": before} if before else None)
        response.raise_for_status()
        page = HTMLParser(response.text)
        if not page.css(".tgme_widget_message[data-post]"):
            raise DownloadError(f"Веб-превью {self._channel} не содержит доступных публикаций")
        return page

    async def resolve_channel_id(self) -> int:
        self._latest = await self._page()
        # shortcut: ID берётся из data-view веб-превью, при изменении разметки потребуется обновить парсер.
        token = self._latest.css_first(".tgme_widget_message[data-view]")
        if token is None:
            raise DownloadError("Telegram web preview has no channel ID")
        encoded = token.attributes["data-view"]
        channel_id = abs(int(json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["c"]))
        if not channel_id:
            raise DownloadError("Telegram web preview has an invalid channel ID")
        return channel_id

    def _posts(self, page: HTMLParser) -> list[CollectedPost]:
        posts = []
        self._media_urls = {}
        for node in page.css(".tgme_widget_message[data-post]"):
            channel, external_id = node.attributes["data-post"].rsplit("/", 1)
            if channel.lower() != self._channel.lower():
                raise DownloadError("Telegram web preview returned another channel")
            message_ids = {int(external_id)}
            media_urls = []
            for media in node.css("a.tgme_widget_message_photo_wrap, video.js-message_video"):
                if media.tag == "video":
                    url = media.attributes.get("src")
                    media_type = "video"
                else:
                    match = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)", media.attributes.get("style", ""))
                    url = match.group(1) if match else None
                    media_type = "photo"
                if not url:
                    continue
                if urlsplit(url).scheme != "https":
                    raise DownloadError("Telegram web preview returned an invalid media URL")
                media_urls.append((url, media_type))
            for link in node.css("a.grouped_media_wrap[href]"):
                path = urlsplit(link.attributes["href"]).path
                if path.startswith(f"/{self._channel}/"):
                    message_ids.add(int(path.rsplit("/", 1)[1]))
            text_node = node.css_first(".tgme_widget_message_text")
            if text_node is not None:
                for br in text_node.css("br"):
                    br.replace_with("\n")
            text = text_node.text().strip() if text_node is not None else ""
            published_at = datetime.fromisoformat(node.css_first(".tgme_widget_message_date time").attributes["datetime"])
            if published_at.tzinfo is None:
                raise DownloadError("Telegram web preview returned a date without timezone")
            forwarded = node.css_first(".tgme_widget_message_forwarded_from a[href]")
            forwarded_url = forwarded.attributes["href"] if forwarded is not None else None
            reactions = node.css(".tgme_reaction")
            reactions_count = sum(self._counter(reaction.text()) for reaction in reactions) if reactions else None
            replies = node.css_first(".tgme_widget_message_replies")
            original_url = f"https://t.me/{self._channel}/{external_id}"
            posts.append(CollectedPost(
                external_id=external_id, all_message_ids=sorted(message_ids), text=text,
                published_at=published_at, edited_at=None, original_url=original_url,
                media_refs=[(f"tgweb:{self._channel}:{external_id}:{index}", kind)
                            for index, (_, kind) in enumerate(media_urls)],
                reactions_count=reactions_count,
                comments_count=self._counter(replies.text()) if replies is not None else None,
                forwarded_from_url=forwarded_url,
                raw_payload={
                    "message_ids": sorted(message_ids), "text": text,
                    "published_at": published_at.isoformat(), "edited_at": None,
                    "original_url": original_url, "forwarded_from_url": forwarded_url,
                },
            ))
            # URL живёт только до скачивания; в БД сохраняется стабильная ссылка на пост и номер вложения.
            self._media_urls[external_id] = media_urls
        return sorted(posts, key=lambda post: int(post.external_id))

    @staticmethod
    def _counter(value: str) -> int:
        match = re.search(r"([\d]+(?:[.,]\d+)?)\s*([KM]?)", value.upper())
        if not match:
            return 0
        return int(float(match.group(1).replace(",", ".")) * {"": 1, "K": 1000, "M": 1000000}[match.group(2)])

    async def iter_history(
        self, *, min_id: int = 0, max_id: int = 0, reverse: bool = False,
        offset_date: datetime | None = None,
    ):
        page = await self._page(before=max_id) if max_id else self._latest or await self._page()
        pending = {}
        before = max_id
        cutoff = self._since or offset_date
        while True:
            posts = self._posts(page)
            for post in reversed(posts):
                if int(post.external_id) <= min_id or (max_id and int(post.external_id) >= max_id):
                    continue
                if cutoff is not None and post.published_at < cutoff:
                    continue
                if reverse:
                    pending[int(post.external_id)] = post
                else:
                    yield post
            oldest = int(posts[0].external_id)
            more = page.css_first(".tme_messages_more[data-before]")
            if (oldest <= min_id or more is None
                    or (cutoff is not None and posts[0].published_at < cutoff)
                    or (reverse and not min_id and cutoff is None)):
                break
            next_before = int(more.attributes["data-before"])
            if next_before >= before and before:
                raise DownloadError("Telegram web preview pagination did not advance")
            before = next_before
            await asyncio.sleep(1)
            page = await self._page(before=before)
        for post_id in sorted(pending):
            yield pending[post_id]

    async def media_url(self, message_id: int, index: int) -> str:
        for post in self._posts(await self._page(message_id=message_id)):
            if post.external_id == str(message_id):
                urls = self._media_urls[post.external_id]
                if 0 <= index < len(urls):
                    return urls[index][0]
        raise DownloadError("Telegram public attachment is unavailable or changed")

    async def iter_preview(self):
        async for post in self.iter_history():
            yield TelegramPostPreview(
                external_id=post.external_id, all_message_ids=post.all_message_ids,
                text=post.text, published_at=post.published_at, original_url=post.original_url,
                media=[TelegramMediaPreview(url=url, media_type=kind)
                       for url, kind in self._media_urls[post.external_id]],
                reactions_count=post.reactions_count, comments_count=post.comments_count,
                forwarded_from_url=post.forwarded_from_url,
            )
