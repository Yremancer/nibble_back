
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.config import NormalizationRule
from src.aggregator.models import RawItemKind
from src.aggregator.normalize.text import content_hash, normalize_for_hash
from src.aggregator.pipeline.normalize_stage import normalize_raw_item
from src.aggregator.repository import MediaAttachmentRepository, RawItemRepository

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

    raw_items_repo = RawItemRepository(session)
    attachments_repo = MediaAttachmentRepository(session)

    item, changed, is_new = await raw_items_repo.upsert_raw_item(
        kind=RawItemKind.TELEGRAM_POST.value,
        source_key=source_key,
        external_id=external_id,
        raw_payload=raw_payload,
        content_hash=content_hash(normalize_for_hash(raw_text)),
        parser_version=parser_version,
    )

    for index, (ref, media_type) in enumerate(media_refs):
        await attachments_repo.upsert(item.id, index, ref, media_type)

    if changed:
        await normalize_raw_item(session, item.id, raw_text, boilerplate_rules)

    return item.id, changed, is_new
