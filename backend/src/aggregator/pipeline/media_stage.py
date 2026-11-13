
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import ProcessingStage
from src.aggregator.repository import MediaAttachmentRepository, TaskRepository
from src.aggregator.media import MediaService
from src.exceptions import AppError

logger = logging.getLogger(__name__)


async def process_media_tasks(
    session: AsyncSession, media_service: MediaService, limit: int
) -> dict:
    tasks_repo = TaskRepository(session)
    attachments_repo = MediaAttachmentRepository(session)

    tasks = await tasks_repo.claim_pending(ProcessingStage.MEDIA, limit)
    done = failed = 0

    for task in tasks:
        try:
            attachments = await attachments_repo.pending_for_item(task.raw_item_id)
            for attachment in attachments:
                try:
                    async with session.begin_nested():
                        media_file = await media_service.store_from_url(attachment.source_ref)
                        await attachments_repo.mark_uploaded(attachment, media_file.id)
                except AppError as exc:
                    await attachments_repo.mark_failed(attachment, str(exc))
                    logger.warning(
                        "media download failed raw_item=%s attachment=%s: %s",
                        task.raw_item_id,
                        attachment.attachment_index,
                        exc,
                    )

            await tasks_repo.mark_done(task)
            await tasks_repo.enqueue(task.raw_item_id, ProcessingStage.PUBLISH)
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("media stage failed for raw_item %s", task.raw_item_id)
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1

    return {"done": done, "failed": failed}
