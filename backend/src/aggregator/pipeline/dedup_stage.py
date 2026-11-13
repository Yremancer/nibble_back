import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.dedup.pipeline import resolve_duplicate
from src.aggregator.models import AggRawItem, ProcessingStage
from src.aggregator.repository import MediaAttachmentRepository, RawItemRepository, TaskRepository

logger = logging.getLogger(__name__)


async def process_dedup_tasks(session: AsyncSession, limit: int) -> dict:
    tasks_repo = TaskRepository(session)
    raw_items_repo = RawItemRepository(session)

    # Serialize decisions so concurrent batches see the previous canonical choice.
    await session.execute(text("SELECT pg_advisory_xact_lock(731912, 1)"))
    tasks = await tasks_repo.claim_pending(ProcessingStage.DEDUP, limit)
    done = failed = duplicates = 0

    for task in tasks:
        raw_item_id = task.raw_item_id
        try:
            async with session.begin_nested():
                raw_item: AggRawItem | None = await session.get(AggRawItem, task.raw_item_id)
                if raw_item is None:
                    await tasks_repo.mark_failed(task, "raw_item не найден")
                    failed += 1
                    continue

                content_version = await raw_items_repo.get_current_content_version(
                    task.raw_item_id
                )
                normalized_text = (content_version.normalized_text if content_version else "") or ""

                attachments = await MediaAttachmentRepository(session).all_for_item(raw_item.id)
                outcome = await resolve_duplicate(
                    session,
                    task.raw_item_id,
                    raw_item.content_hash,
                    normalized_text,
                    raw_item.first_seen_at,
                    media_file_ids=[a.media_file_id for a in attachments if a.media_file_id is not None],
                )

                if outcome.is_duplicate and raw_item.post_id is None:
                    duplicates += 1
                    await tasks_repo.mark_done(task)
                    continue

                await tasks_repo.mark_done(task)
                await tasks_repo.enqueue(task.raw_item_id, ProcessingStage.PUBLISH)
                done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("dedup stage failed for raw_item %s", raw_item_id)
            await session.refresh(task)
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1

    return {"done": done, "failed": failed, "duplicates": duplicates}
