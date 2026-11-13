"""Реализация команд CLI. Каждая команда открывает собственную сессию БД и
закрывает внешние клиенты по завершении, чтобы `doctor`/`sync` можно было
запускать независимо друг от друга."""

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from sqlalchemy import select, text
from src.aggregator.config import aggregator_settings, load_sources_config
from src.aggregator.models import ProcessingStage
from src.database.database import async_session_maker
from src.llm.client import DeepSeekClient
from src.llm.settings import llm_settings
from src.models.listing import Listing
from src.models.post import Post
from src.aggregator.doctor import cmd_doctor
from src.storage.repository import FileRepository
from src.storage.service import FileService
from src.storage.setup import create_storage_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _http_client():
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        yield client


async def cmd_auth_telegram() -> None:
    from src.aggregator.sources.telegram_auth import run_telegram_auth

    await run_telegram_auth()


_PIPELINE_STAGES = [
    ProcessingStage.CLASSIFY,
    ProcessingStage.RESOLVE,
    ProcessingStage.DEDUP,
    ProcessingStage.MEDIA,
    ProcessingStage.PUBLISH,
]


async def _drain_pipeline(limit_per_stage: int = 200) -> dict:
    """Прогоняет очередь задач по всем этапам после ingest. Каждый этап
    независим: сбой DeepSeek/S3 на одной публикации не останавливает
    остальные и не теряет задачу (она останется pending/failed)."""
    stats = {}
    for stage in _PIPELINE_STAGES:
        stats[stage.value] = await _run_stage(stage, limit_per_stage)
    return stats


async def cmd_sync(source: str, limit: int | None, pages: int | None, dry_run: bool) -> None:
    stats_all = {}
    if source in ("all", "telegram"):
        stats_all["telegram"] = await _run_telegram_sync(mode="sync", since=None, limit=limit)
    if source in ("all", "farpost"):
        stats_all["farpost"] = await _run_farpost_sync(max_pages=pages, max_listings=limit)
    if not dry_run:
        stats_all["pipeline"] = await _drain_pipeline()
    print(json.dumps(stats_all, ensure_ascii=False, indent=2, default=str))


async def cmd_backfill(source: str, since, limit: int | None, pages: int | None) -> None:
    if source == "telegram":
        stats = await _run_telegram_sync(mode="backfill", since=since, limit=limit)
    elif source == "farpost":
        stats = await _run_farpost_sync(max_pages=pages, max_listings=limit)
    elif source == "fishing_vl":
        stats = await _run_fishing_vl_sync(limit=limit)
    else:
        stats = {}

    if source in ("telegram", "farpost"):
        stats = {"ingest": stats, "pipeline": await _drain_pipeline()}

    print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))


async def _run_telegram_sync(mode: str, since, limit: int | None) -> dict:
    if not aggregator_settings.is_telegram_configured:
        return {"error": "TELEGRAM_API_ID/TELEGRAM_API_HASH не заданы"}

    from telethon import TelegramClient

    from src.aggregator.sources.telegram_sync import sync_telegram_source

    sources_config = load_sources_config()
    client = TelegramClient(
        aggregator_settings.prepare_telegram_session(),
        aggregator_settings.TELEGRAM_API_ID,
        aggregator_settings.TELEGRAM_API_HASH,
    )
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return {"error": "Telegram-сессия не авторизована, выполните auth-telegram"}

    all_stats = {}
    try:
        for tg_source in sources_config.telegram:
            if not tg_source.is_active:
                continue
            try:
                async with async_session_maker() as session:
                    stats = await sync_telegram_source(
                        session, client, tg_source, sources_config,
                        mode=mode, since=since, limit=limit,
                    )
                    await session.commit()
                all_stats[tg_source.channel] = stats
            except Exception:
                logger.exception("telegram sync failed for %s", tg_source.channel)
                all_stats[tg_source.channel] = {"errors": 1}
    finally:
        await client.disconnect()

    return all_stats


async def _run_farpost_sync(max_pages: int | None, max_listings: int | None) -> dict:
    from src.aggregator.sources.farpost_collector import FarpostCollector
    from src.aggregator.sources.farpost_sync import sync_farpost

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True
    ) as http_client:
        collector = FarpostCollector(
            http_client, aggregator_settings.FARPOST_BASE_URL, aggregator_settings.FARPOST_CITY_PATH
        )
        async with async_session_maker() as session:
            stats = await sync_farpost(
                session, collector,
                max_pages=max_pages, max_listings=max_listings,
                city_path=aggregator_settings.FARPOST_CITY_PATH,
            )
            await session.commit()
    return stats


async def _run_fishing_vl_sync(limit: int | None) -> dict:
    from src.aggregator.sources.fishing_vl_collector import FishingVlCollector
    from src.aggregator.sources.fishing_vl_sync import sync_fishing_vl_spots

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as http_client:
        collector = FishingVlCollector(http_client, aggregator_settings.FISHING_VL_BASE_URL)
        async with async_session_maker() as session:
            stats = await sync_fishing_vl_spots(session, collector, limit=limit)
            await session.commit()
    return stats


async def cmd_reprocess(stage: str, limit: int) -> None:
    stats = await _run_stage(ProcessingStage(stage), limit)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


async def cmd_retry_failed(stage: str, limit: int) -> None:
    from src.aggregator.repository import TaskRepository

    async with async_session_maker() as session:
        tasks_repo = TaskRepository(session)
        requeued = await tasks_repo.claim_failed(ProcessingStage(stage), limit)
        await session.commit()
    print(json.dumps({"requeued": len(requeued)}, ensure_ascii=False, indent=2))


async def _run_stage(stage: ProcessingStage, limit: int) -> dict:
    async with async_session_maker() as session:
        if stage == ProcessingStage.CLASSIFY:
            from src.aggregator.pipeline.classify import process_classify_tasks

            async with _http_client() as http_client:
                client = DeepSeekClient(llm_settings, http_client)
                stats = await process_classify_tasks(session, client, llm_settings, limit)
        elif stage == ProcessingStage.RESOLVE:
            from src.aggregator.pipeline.resolve import process_resolve_tasks

            stats = await process_resolve_tasks(session, limit)
        elif stage == ProcessingStage.DEDUP:
            from src.aggregator.pipeline.dedup_stage import process_dedup_tasks

            stats = await process_dedup_tasks(session, limit)
        elif stage == ProcessingStage.MEDIA:
            from src.aggregator.pipeline.media_stage import process_media_tasks
            from src.aggregator.media import MediaService

            async with _http_client() as http_client, create_storage_client() as storage_client:
                files = FileService(FileRepository(session), storage_client)
                telegram = None
                if aggregator_settings.is_telegram_configured:
                    from telethon import TelegramClient

                    telegram = TelegramClient(
                        aggregator_settings.prepare_telegram_session(),
                        aggregator_settings.TELEGRAM_API_ID,
                        aggregator_settings.TELEGRAM_API_HASH,
                    )
                try:
                    media_service = MediaService(files, http_client, telegram)
                    stats = await process_media_tasks(session, media_service, limit)
                finally:
                    if telegram is not None:
                        await telegram.disconnect()
        elif stage == ProcessingStage.PUBLISH:
            from src.aggregator.pipeline.publish_stage import process_publish_tasks

            stats = await process_publish_tasks(session, limit)
        else:
            stats = {"error": f"этап {stage} не поддерживает ручной запуск напрямую"}

        await session.commit()
    return stats


async def cmd_export(kind: str, output: str | None) -> None:
    output_path = Path(output) if output else Path(f"/app/data/export_{kind}.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_session_maker() as session:
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            if kind == "posts":
                result = await session.execute(select(Post))
                for post in result.scalars():
                    f.write(json.dumps(_post_to_dict(post), ensure_ascii=False, default=str) + "\n")
                    count += 1
            elif kind == "listings":
                result = await session.execute(select(Listing))
                for listing in result.scalars():
                    f.write(json.dumps(_listing_to_dict(listing), ensure_ascii=False, default=str) + "\n")
                    count += 1

    print(json.dumps({"exported": count, "path": str(output_path)}, ensure_ascii=False))


def _post_to_dict(post: Post) -> dict:
    return {
        "id": post.id, "source_id": post.source_id, "kind": post.kind,
        "status": post.status, "text": post.text, "spot_id": post.spot_id,
        "method_id": post.method_id, "fishing_date": post.fishing_date,
        "event_date": post.event_date, "published_at": post.published_at,
        "original_url": post.original_url,
    }


def _listing_to_dict(listing: Listing) -> dict:
    return {
        "id": listing.id, "farpost_id": listing.farpost_id, "title": listing.title,
        "price_rub": listing.price_rub, "price_raw": listing.price_raw,
        "city_id": listing.city_id, "category_id": listing.category_id,
        "is_active": listing.is_active, "state": listing.state, "url": listing.url,
    }


async def cmd_status() -> None:
    from src.aggregator.models import AggCursor, AggProcessingTask, AggRun

    async with async_session_maker() as session:
        cursors = (await session.execute(select(AggCursor))).scalars().all()
        pending_counts = {}
        failed_counts = {}
        result = await session.execute(
            text(
                "SELECT stage, status, count(*) FROM agg_processing_tasks "
                "GROUP BY stage, status"
            )
        )
        for stage, status, count in result:
            if status == "pending":
                pending_counts[stage] = count
            elif status == "failed":
                failed_counts[stage] = count

        last_runs = (
            await session.execute(select(AggRun).order_by(AggRun.started_at.desc()).limit(5))
        ).scalars().all()

    output = {
        "cursors": [
            {"source_key": c.source_key, "type": c.cursor_type, "position": c.position}
            for c in cursors
        ],
        "pending_tasks": pending_counts,
        "failed_tasks": failed_counts,
        "last_runs": [
            {"source_key": r.source_key, "command": r.command, "status": r.status}
            for r in last_runs
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
