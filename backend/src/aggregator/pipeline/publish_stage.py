"""Этап публикации: собирает Post из классификации, разрешённых
справочников и загруженных медиафайлов. decision=review или
needs_media_analysis без доступного провайдера ставит статус moderation,
не публикуя автоматически."""

import logging

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import AggDedupDecision, AggRawItem, ProcessingStage
from src.aggregator.normalize.dates import resolve_fishing_date
from src.aggregator.repository import (
    ClassificationRepository,
    MediaAttachmentRepository,
    RawItemRepository,
    TaskRepository,
)
from src.aggregator.writer.media import PostMediaWriter
from src.aggregator.writer.posts import PostWriter
from src.llm.schemas import ClassificationResult
from src.llm.settings import llm_settings
from src.models.post import PostKind, PostStatus

logger = logging.getLogger(__name__)


def _post_kind_for_category(category: str | None) -> PostKind:
    if category == "incident":
        return PostKind.INCIDENT
    if category == "useful_info":
        return PostKind.USEFUL_INFO
    return PostKind.FISHING_REPORT


def _status_for_decision(decision: str, needs_media_analysis: bool) -> PostStatus:
    if decision == "review" or needs_media_analysis:
        return PostStatus.MODERATION
    return PostStatus.PUBLISHED


async def process_publish_tasks(session: AsyncSession, limit: int) -> dict:
    tasks_repo = TaskRepository(session)
    raw_items_repo = RawItemRepository(session)
    classifications_repo = ClassificationRepository(session)
    attachments_repo = MediaAttachmentRepository(session)
    post_writer = PostWriter(session)
    media_writer = PostMediaWriter(session)

    tasks = await tasks_repo.claim_pending(ProcessingStage.PUBLISH, limit)
    done = failed = 0

    for task in tasks:
        raw_item_id = task.raw_item_id
        try:
            async with session.begin_nested():
                raw_item: AggRawItem | None = await session.get(AggRawItem, task.raw_item_id)
                if raw_item is None:
                    await tasks_repo.mark_done(task)
                    done += 1
                    continue

                if raw_item.kind == "farpost_listing":
                    from src.aggregator.pipeline.publish_listings import publish_pending_listings

                    result = await publish_pending_listings(session, [raw_item.id])
                    if result["failed"]:
                        await tasks_repo.mark_failed(task, "publish_listing failed")
                        failed += 1
                    else:
                        await tasks_repo.mark_done(task)
                        done += 1
                    continue

                if raw_item.kind != "telegram_post":
                    await tasks_repo.mark_done(task)
                    done += 1
                    continue

                duplicate = await session.scalar(select(exists().where(
                    AggDedupDecision.item_a_id == raw_item.id,
                    AggDedupDecision.decision == "duplicate",
                )))
                if duplicate and raw_item.post_id is None:
                    await tasks_repo.mark_done(task)
                    done += 1
                    continue

                content_version = await raw_items_repo.get_current_content_version(
                    task.raw_item_id
                )
                cached = await classifications_repo.get_cached(
                    content_version.id, llm_settings.DEEPSEEK_MODEL, llm_settings.PROMPT_VERSION
                )
                if cached is None:
                    await tasks_repo.mark_failed(task, "нет результата классификации")
                    failed += 1
                    continue

                result = ClassificationResult.model_validate(cached.result)
                if result.decision.value == "discard":
                    await tasks_repo.mark_done(task)
                    done += 1
                    continue

                payload = raw_item.raw_payload
                published_at = payload["published_at"]
                from datetime import datetime

                published_dt = datetime.fromisoformat(published_at)

                fishing_date = None
                if result.category and result.category.value == "fishing_report":
                    fishing_date = resolve_fishing_date(result.fishing_date, published_dt)

                event_date = None
                if result.category and result.category.value == "incident":
                    event_date = resolve_fishing_date(result.event_date, published_dt)

                from src.aggregator.pipeline.resolve import resolve_classification
                from src.aggregator.resolve.dictionary import DictionaryResolver

                resolver = DictionaryResolver(session)
                resolved = await resolve_classification(resolver, result)
                needs_review = await session.scalar(select(exists().where(
                    AggDedupDecision.item_a_id == raw_item.id,
                    AggDedupDecision.decision == "uncertain",
                )))

                post = await post_writer.upsert_post(
                    existing_post_id=raw_item.post_id,
                    source_id=payload["source_id"],
                    external_post_id=payload["external_post_id"],
                    original_url=payload.get("original_url"),
                    text=content_version.normalized_text or "",
                    published_at=published_dt,
                    kind=_post_kind_for_category(
                        result.category.value if result.category else None
                    ),
                    status=_status_for_decision(
                        result.decision.value, result.needs_media_analysis or needs_review
                    ),
                    fishing_date=fishing_date,
                    event_date=event_date,
                    spot_id=resolved.spot_id,
                    method_id=resolved.method_id,
                    bait=result.bait,
                    conditions=result.conditions,
                    tg_reactions_count=payload.get("reactions_count"),
                    tg_comments_count=payload.get("comments_count"),
                )

                if raw_item.post_id is None:
                    await raw_items_repo.link_post(raw_item.id, post.id)

                catches = resolved.species if post.kind == "fishing_report" else []
                await post_writer.set_catches(post.id, catches)

                attachments = await attachments_repo.all_for_item(task.raw_item_id)
                media_items = [
                    {
                        "media_file_id": a.media_file_id,
                        "type": a.media_type,
                        "sort_order": a.attachment_index,
                    }
                    for a in attachments
                    if a.media_file_id is not None
                ]
                await media_writer.set_media(post.id, media_items)

                await tasks_repo.mark_done(task)
                done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("publish stage failed for raw_item %s", raw_item_id)
            await session.refresh(task)
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1

    return {"done": done, "failed": failed}
