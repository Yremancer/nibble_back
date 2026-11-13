"""Приём сырой публикации источника: сохраняет оригинал, продвигает
позицию обхода (курсор) отдельно от последующей обработки, ставит задачу
нормализации. Сбой нормализации/классификации не блокирует сохранение
следующей публикации (см. ТЗ, раздел 4)."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.config import NormalizationRule
from src.aggregator.models import ProcessingStage, RawItemKind
from src.aggregator.normalize.text import content_hash, normalize_for_hash
from src.aggregator.pipeline.normalize_stage import normalize_raw_item
from src.aggregator.repository import MediaAttachmentRepository, RawItemRepository, TaskRepository

logger = logging.getLogger(__name__)


async def ingest_telegram_post(
    session: AsyncSession,
    *,
    source_key: str,
    external_id: str,
    raw_payload: dict,
    raw_text: str,
    media_refs: list[tuple[str, str]],
    boilerplate_rules: list[NormalizationRule],
    parser_version: str,
) -> tuple[int, bool, bool]:
    """media_refs: [(source_ref, media_type)] в исходном порядке альбома.
    Возвращает (raw_item_id, content_changed, is_new)."""

    raw_items_repo = RawItemRepository(session)
    attachments_repo = MediaAttachmentRepository(session)

    item, changed, is_new = await raw_items_repo.upsert_raw_item(
        kind=RawItemKind.TELEGRAM_POST.value,
        source_key=source_key,
        external_id=external_id,
        raw_payload={**raw_payload, "text": raw_text, "media_refs": [list(ref) for ref in media_refs]},
        content_hash=content_hash(normalize_for_hash(raw_text)),
        parser_version=parser_version,
    )

    for index, (ref, media_type) in enumerate(media_refs):
        await attachments_repo.upsert(item.id, index, ref, media_type)
    await attachments_repo.delete_after(item.id, len(media_refs))

    if changed:
        current = await raw_items_repo.get_current_content_version(item.id)
        if item.post_id is not None and current is not None and current.original_text == raw_text:
            await TaskRepository(session).enqueue(item.id, ProcessingStage.MEDIA)
            return item.id, changed, is_new
        # нормализация выполняется сразу (это чистая функция, не внешний
        # вызов): дальше в очередь ставится только classify, т.к. сбой
        # внешних сервисов (DeepSeek/S3) не должен блокировать ingest.
        await normalize_raw_item(session, item.id, raw_text, boilerplate_rules)
    elif await attachments_repo.pending_for_item(item.id):
        await TaskRepository(session).enqueue(item.id, ProcessingStage.MEDIA)

    return item.id, changed, is_new
