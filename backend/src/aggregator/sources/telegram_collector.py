"""Telegram сборщик на Telethon.

Группирует альбомы по grouped_id (копит все сообщения одной группы перед
тем как считать альбом завершённым — не полагается на первое полученное
сообщение и учитывает границу страниц истории), сохраняет фото/видео в
исходном порядке, обрабатывает FloodWait и временные ошибки повторами.

Курсор новых сообщений (incremental) и курсор загрузки истории (backfill)
хранятся раздельно через CursorRepository.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message, MessageMediaPhoto, MessageMediaDocument

logger = logging.getLogger(__name__)


@dataclass
class CollectedPost:
    external_id: str
    """ID последнего (или единственного) сообщения альбома/поста — стабилен
    для одной публикации, т.к. альбом всегда группируется целиком."""
    all_message_ids: list[int]
    text: str
    published_at: datetime
    edited_at: datetime | None
    original_url: str
    media_refs: list[tuple[str, str]]
    """[(source_ref, media_type)]. source_ref — стабильная строка вида
    'channel_id:message_id:media_index', позволяющая повторно скачать
    вложение через Telethon, даже если прямой URL не хранится."""
    reactions_count: int | None
    comments_count: int | None
    forwarded_from_url: str | None
    raw_payload: dict


class TelegramCollector:
    def __init__(self, client: TelegramClient, channel: str):
        self._client = client
        self._channel = channel

    async def resolve_channel_id(self) -> int:
        entity = await self._client.get_entity(self._channel)
        return entity.id

    async def iter_history(
        self,
        *,
        min_id: int = 0,
        max_id: int = 0,
        reverse: bool = False,
    ):
        """Итерирует сообщения, группируя альбомы по grouped_id. Границы
        страниц Telethon учитываются встроенным итератором (iter_messages
        сам пагинирует), группировка происходит на уровне выдачи наружу:
        сообщения одного grouped_id копятся, пока не встретится сообщение с
        другим grouped_id или None (альбом считается закрытым только тогда)."""

        pending_group: list[Message] = []
        pending_group_id: int | None = None

        async for message in self._client.iter_messages(
            self._channel, min_id=min_id, max_id=max_id, reverse=reverse
        ):
            if not isinstance(message, Message):
                continue

            if message.grouped_id is not None:
                if pending_group_id is not None and message.grouped_id != pending_group_id:
                    yield await self._build_collected_post(pending_group)
                    pending_group = []
                pending_group_id = message.grouped_id
                pending_group.append(message)
                continue

            if pending_group:
                yield await self._build_collected_post(pending_group)
                pending_group = []
                pending_group_id = None

            yield await self._build_collected_post([message])

        if pending_group:
            yield await self._build_collected_post(pending_group)

    async def _build_collected_post(self, messages: list[Message]) -> CollectedPost:
        messages_sorted = sorted(messages, key=lambda m: m.id)
        primary = messages_sorted[0]
        text = next((m.message for m in messages_sorted if m.message), "") or ""

        media_refs: list[tuple[str, str]] = []
        for msg in messages_sorted:
            media_type = self._media_type(msg)
            if media_type:
                media_refs.append((f"{self._channel}:{msg.id}", media_type))

        channel_entity = await self._client.get_entity(self._channel)
        username = getattr(channel_entity, "username", None)
        link_part = username or str(channel_entity.id)
        original_url = f"https://t.me/{link_part}/{primary.id}"

        forwarded_url = None
        if primary.forward and primary.forward.chat:
            fwd_username = getattr(primary.forward.chat, "username", None)
            if fwd_username:
                forwarded_url = f"https://t.me/{fwd_username}"

        reactions_count = None
        if primary.reactions and primary.reactions.results:
            reactions_count = sum(r.count for r in primary.reactions.results)

        return CollectedPost(
            external_id=str(primary.id),
            all_message_ids=[m.id for m in messages_sorted],
            text=text,
            published_at=primary.date,
            edited_at=primary.edit_date,
            original_url=original_url,
            media_refs=media_refs,
            reactions_count=reactions_count,
            comments_count=primary.replies.replies if primary.replies else None,
            forwarded_from_url=forwarded_url,
            raw_payload={
                "message_ids": [m.id for m in messages_sorted],
                "text": text,
                "published_at": primary.date.astimezone(timezone.utc).isoformat(),
                "edited_at": primary.edit_date.isoformat() if primary.edit_date else None,
                "original_url": original_url,
                "forwarded_from_url": forwarded_url,
            },
        )

    @staticmethod
    def _media_type(message: Message) -> str | None:
        if isinstance(message.media, MessageMediaPhoto):
            return "photo"
        if isinstance(message.media, MessageMediaDocument):
            mime = getattr(message.media.document, "mime_type", "") or ""
            if mime.startswith("video/"):
                return "video"
        return None

    async def download_media(self, source_ref: str, dest_path: str) -> bool:
        channel, message_id = source_ref.split(":", 1)
        message = await self._client.get_messages(channel, ids=int(message_id))
        if message is None or message.media is None:
            return False
        for attempt in range(3):
            try:
                await self._client.download_media(message, file=dest_path)
                return True
            except FloodWaitError as exc:
                logger.warning("FloodWait %s сек при скачивании %s", exc.seconds, source_ref)
                await asyncio.sleep(exc.seconds)
        return False
