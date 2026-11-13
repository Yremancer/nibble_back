"""Этап медиа: скачивает вложения (по стабильной ссылке источника, не по
истёкшему прямому URL) и загружает в S3 через MediaService. Сбой по одному
вложению не блокирует остальные и не блокирует последующую публикацию поста
без медиа-вложений, если они были необязательны."""

import logging
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import AggRawItem, ProcessingStage
from src.aggregator.repository import MediaAttachmentRepository, TaskRepository
from src.aggregator.media import MediaService

logger = logging.getLogger(__name__)


async def process_media_tasks(
    session: AsyncSession, media_service: MediaService, limit: int
) -> dict:
    tasks_repo = TaskRepository(session)
    attachments_repo = MediaAttachmentRepository(session)

    tasks = await tasks_repo.claim_pending(ProcessingStage.MEDIA, limit)
    done = failed = 0

    for task in tasks:
        raw_item_id = task.raw_item_id
        try:
            async with session.begin_nested():
                attachments = await attachments_repo.pending_for_item(raw_item_id)
                errors = []
                for attachment in attachments:
                    attachment_index = attachment.attachment_index
                    try:
                        async with session.begin_nested():
                            if urlsplit(attachment.source_ref).scheme in ("http", "https"):
                                media_file = await media_service.store_from_url(attachment.source_ref)
                            else:
                                media_file = await media_service.store_from_telegram(attachment.source_ref)
                            await attachments_repo.mark_uploaded(attachment, media_file.id)
                    except Exception as exc:
                        await session.refresh(attachment)
                        await attachments_repo.mark_failed(attachment, str(exc))
                        errors.append(str(exc))
                        logger.warning(
                            "media download failed raw_item=%s attachment=%s: %s",
                            raw_item_id, attachment_index, exc,
                        )

                if errors:
                    await tasks_repo.mark_failed(task, "; ".join(errors))
                else:
                    await tasks_repo.mark_done(task)
                raw_item = await session.get(AggRawItem, raw_item_id)
                next_stage = (ProcessingStage.DEDUP if raw_item.kind == "telegram_post"
                              else ProcessingStage.PUBLISH)
                await tasks_repo.enqueue(raw_item_id, next_stage)
            if errors:
                failed += 1
            else:
                done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("media stage failed for raw_item %s", raw_item_id)
            await session.refresh(task)
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1

    return {"done": done, "failed": failed}
