"""Запуск синхронизации Telegram: поддерживает incremental (sync) и
backfill (backfill --since) режимы с раздельными курсорами.

shortcut: один процесс на файл сессии, без файловой блокировки — если нужно
запускать несколько источников параллельно, завести отдельные сессии на
канал. Upgrade: добавить lock-файл или семафор в БД при реальной
конкурентности.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from src.aggregator.config import (
    NormalizationRule,
    SourcesConfig,
    TelegramSourceConfig,
    aggregator_settings,
)
from src.aggregator.pipeline.ingest import ingest_telegram_post
from src.aggregator.repository import CursorRepository
from src.aggregator.sources.telegram_collector import CollectedPost, TelegramCollector
from src.aggregator.sources.telegram_public import PublicTelegramCollector
from src.models.post import Source, SourceType

logger = logging.getLogger(__name__)

PARSER_VERSION = "telegram_v1"


async def ensure_source(session: AsyncSession, cfg: TelegramSourceConfig, channel_id: int) -> Source:
    external_id = str(channel_id)
    result = await session.execute(
        select(Source).where(
            Source.type == SourceType.TELEGRAM.value, Source.external_id == external_id
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        source = Source(
            type=SourceType.TELEGRAM.value,
            name=cfg.name,
            url=f"https://t.me/{cfg.channel}",
            external_id=external_id,
            city_id=cfg.city_id,
            is_active=cfg.is_active,
        )
        session.add(source)
        await session.flush()
    return source


async def sync_telegram_source(
    session: AsyncSession,
    client: TelegramClient | httpx.AsyncClient,
    cfg: TelegramSourceConfig,
    sources_config: SourcesConfig,
    *,
    mode: str,
    since: datetime | None,
    limit: int | None,
) -> dict:
    if isinstance(client, httpx.AsyncClient):
        public_since = None
        if mode == "backfill":
            public_since = since or datetime.now(timezone.utc) - timedelta(
                days=aggregator_settings.AGG_BACKFILL_DEPTH_DAYS,
            )
        collector = PublicTelegramCollector(client, cfg.channel, since=public_since)
    else:
        collector = TelegramCollector(client, cfg.channel)
    channel_id = await collector.resolve_channel_id()
    source = await ensure_source(session, cfg, channel_id)

    source_key = f"telegram:{channel_id}"
    cursor_repo = CursorRepository(session)
    boilerplate_rules = [
        NormalizationRule.model_validate(r.model_dump())
        for r in sources_config.normalization.get(cfg.channel, [])
    ]

    stats = {"fetched": 0, "created": 0, "updated": 0, "errors": 0}

    cursor_type = "backfill" if mode == "backfill" else "incremental"
    cursor = await cursor_repo.get(source_key, cursor_type)
    min_id = cursor.get("last_message_id", 0) if cursor else 0

    cursor_blocked = False
    count = 0

    async def save(collected: CollectedPost, *, advance_cursor: bool) -> bool:
        stats["fetched"] += 1
        try:
            async with session.begin_nested():
                _, changed, is_new = await ingest_telegram_post(
                    session,
                    source_key=source_key,
                    external_id=collected.external_id,
                    raw_payload={
                        **collected.raw_payload,
                        "source_id": source.id,
                        "external_post_id": collected.external_id,
                        "channel": cfg.channel,
                        "reactions_count": collected.reactions_count,
                        "comments_count": collected.comments_count,
                    },
                    raw_text=collected.text,
                    media_refs=collected.media_refs,
                    boilerplate_rules=boilerplate_rules,
                    parser_version=PARSER_VERSION,
                )
                if advance_cursor:
                    await cursor_repo.set(
                        source_key, cursor_type,
                        {"last_message_id": max(collected.all_message_ids)},
                    )
            if changed:
                stats["created" if is_new else "updated"] += 1
            return True
        except Exception:
            logger.exception("ingest failed for telegram post %s", collected.external_id)
            stats["errors"] += 1
            return False

    try:
        offset_date = since if mode == "sync" and not cursor else None
        async for collected in collector.iter_history(min_id=min_id, reverse=True, offset_date=offset_date):
            if (
                collected is not None and since is not None
                and collected.published_at < since and mode == "backfill"
            ):
                continue
            if limit is not None and count >= limit:
                break
            count += 1
            if collected is None:
                stats["errors"] += 1
                cursor_blocked = True
                continue
            if not await save(collected, advance_cursor=not cursor_blocked):
                # Следующий запуск должен вернуться к пропуску, даже если записи после него сохранены.
                cursor_blocked = True
    except Exception:
        logger.exception("telegram history failed for %s", cfg.channel)
        stats["errors"] += 1

    if mode == "sync" and min_id:
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=aggregator_settings.AGG_RECHECK_WINDOW_HOURS
        )
        try:
            # Перепроверка не расходует лимит новых записей, иначе малый лимит остановит сбор.
            async for collected in collector.iter_history(max_id=min_id + 1):
                if collected is None:
                    stats["errors"] += 1
                    continue
                if collected.published_at < cutoff:
                    break
                await save(collected, advance_cursor=False)
        except Exception:
            logger.exception("telegram recheck failed for %s", cfg.channel)
            stats["errors"] += 1

    source.last_synced_at = datetime.now(timezone.utc)
    await session.flush()

    return stats
