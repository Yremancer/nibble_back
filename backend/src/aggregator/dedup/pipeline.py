"""Оркестрация решения о дубле для одной сырой публикации.

Правила (см. ТЗ, раздел 11): короткий одинаковый текст недостаточен сам по
себе; одна общая фотография недостаточна; одинаковое место и рыба
недостаточны. Автоматическое объединение происходит только при точном
хеше текста (уровень 2) либо при высоком текстовом сходстве (уровень 4) в
сочетании с пересечением медиа. Остальные случаи — review у человека.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.dedup.service import DedupService
from src.aggregator.models import DedupDecisionKind

_HIGH_TEXT_SIMILARITY_FOR_AUTO = 0.85


@dataclass
class DedupOutcome:
    is_duplicate: bool
    canonical_raw_item_id: int | None
    needs_review: bool
    reason: str


async def resolve_duplicate(
    session: AsyncSession,
    raw_item_id: int,
    content_hash_value: str,
    normalized_text: str,
    published_at,
    media_file_ids: list[int],
) -> DedupOutcome:
    service = DedupService(session)

    exact = await service.find_exact_duplicate(content_hash_value, raw_item_id)
    if exact is not None:
        await service.record_decision(
            raw_item_id,
            exact.id,
            level=2,
            decision=DedupDecisionKind.DUPLICATE,
            reason="точное совпадение нормализованного текста",
            features={"content_hash": content_hash_value},
        )
        return DedupOutcome(True, exact.id, False, "exact_text_hash")

    candidates = await service.find_text_candidates(
        normalized_text, raw_item_id, published_at
    )
    if not candidates:
        return DedupOutcome(False, None, False, "no_candidates")

    media_overlap_ids = await service.find_media_sha_overlap(media_file_ids, raw_item_id)

    best = candidates[0]
    if best.similarity >= _HIGH_TEXT_SIMILARITY_FOR_AUTO and media_overlap_ids:
        await service.record_decision(
            raw_item_id,
            best.raw_item_id,
            level=4,
            decision=DedupDecisionKind.DUPLICATE,
            reason="высокое текстовое сходство и общие медиафайлы",
            features={"similarity": best.similarity, "media_overlap": media_overlap_ids},
        )
        return DedupOutcome(True, best.raw_item_id, False, "high_similarity_with_media")

    for candidate in candidates:
        await service.record_decision(
            raw_item_id,
            candidate.raw_item_id,
            level=4,
            decision=DedupDecisionKind.UNCERTAIN,
            reason="похожий текст без достаточных дополнительных признаков",
            features={"similarity": candidate.similarity},
        )

    return DedupOutcome(False, None, True, "uncertain_candidates")
