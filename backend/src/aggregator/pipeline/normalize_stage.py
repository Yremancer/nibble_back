"""Этап нормализации: строит AggContentVersion из сырого текста и ставит
задачу классификации. Срабатывает как сразу после приёма сырой публикации
(ingest), так и повторно при смене normalization_version (reprocess)."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.config import NormalizationRule
from src.aggregator.models import ProcessingStage
from src.aggregator.normalize.text import normalize_post_text
from src.aggregator.repository import RawItemRepository, TaskRepository

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
