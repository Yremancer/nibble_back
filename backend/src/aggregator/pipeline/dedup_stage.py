import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.dedup.pipeline import resolve_duplicate
from src.aggregator.models import AggRawItem, ProcessingStage
from src.aggregator.repository import RawItemRepository, TaskRepository

logger = logging.getLogger(__name__)


async def process_dedup_tasks(session: AsyncSession, limit: int) -> dict:
    tasks_repo = TaskRepository(session)
    raw_items_repo = RawItemRepository(session)

    tasks = await tasks_repo.claim_pending(ProcessingStage.DEDUP, limit)
    done = failed = duplicates = 0

    for task in tasks:
        try:
            raw_item: AggRawItem | None = await session.get(AggRawItem, task.raw_item_id)
            if raw_item is None:
                await tasks_repo.mark_failed(task, "raw_item не найден")
                failed += 1
                continue

            content_version = await raw_items_repo.get_current_content_version(
                task.raw_item_id
            )
            normalized_text = (content_version.normalized_text if content_version else "") or ""

            outcome = await resolve_duplicate(
                session,
                task.raw_item_id,
                raw_item.content_hash,
                normalized_text,
                raw_item.first_seen_at,
                media_file_ids=[],
            )

            if outcome.is_duplicate:
                duplicates += 1
                await tasks_repo.mark_done(task)
                continue

            await tasks_repo.mark_done(task)
            await tasks_repo.enqueue(task.raw_item_id, ProcessingStage.MEDIA)
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("dedup stage failed for raw_item %s", task.raw_item_id)
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1

    return {"done": done, "failed": failed, "duplicates": duplicates}
