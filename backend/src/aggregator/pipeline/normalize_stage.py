"""Этап нормализации: строит AggContentVersion из сырого текста и ставит
задачу классификации. Срабатывает как сразу после приёма сырой публикации
(ingest), так и повторно при смене normalization_version (reprocess)."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.config import NormalizationRule, load_sources_config
from src.aggregator.models import AggRawItem, ProcessingStage
from src.aggregator.normalize.text import normalize_post_text
from src.aggregator.repository import RawItemRepository, TaskRepository
from src.models.post import Source

logger = logging.getLogger(__name__)


async def normalize_raw_item(
    session: AsyncSession,
    raw_item_id: int,
    raw_text: str,
    boilerplate_rules: list[NormalizationRule],
) -> None:
    raw_items_repo = RawItemRepository(session)
    tasks_repo = TaskRepository(session)

    normalized = normalize_post_text(raw_text, boilerplate_rules)
    await raw_items_repo.add_content_version(
        raw_item_id,
        original_text=normalized["original_text"],
        normalized_text=normalized["normalized_text"],
        removed_boilerplate=normalized["removed_boilerplate"],
        normalization_version=normalized["normalization_version"],
    )
    await tasks_repo.enqueue(raw_item_id, ProcessingStage.CLASSIFY)


async def process_normalize_tasks(session: AsyncSession, limit: int) -> dict:
    repo = TaskRepository(session)
    tasks = await repo.claim_pending(ProcessingStage.NORMALIZE, limit)
    config = load_sources_config()
    done = failed = 0
    for task in tasks:
        raw_item_id = task.raw_item_id
        try:
            async with session.begin_nested():
                item = await session.get(AggRawItem, raw_item_id)
                payload = item.raw_payload
                channel = payload.get("channel")
                if not channel and payload.get("source_id"):
                    source = await session.get(Source, payload["source_id"])
                    channel = source.url.rstrip("/").rsplit("/", 1)[-1] if source and source.url else ""
                rules = config.normalization.get(channel, [
                    NormalizationRule.model_validate(rule) for rule in payload.get("normalization_rules", [])
                ])
                await normalize_raw_item(session, raw_item_id, payload.get("text", ""), rules)
                await repo.mark_done(task)
            done += 1
        except Exception as exc:
            logger.exception("normalize stage failed for raw_item %s", raw_item_id)
            await session.refresh(task)
            await repo.mark_failed(task, str(exc))
            failed += 1
    return {"done": done, "failed": failed}
