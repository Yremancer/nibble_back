
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.dedup.service import DedupService
from src.aggregator.models import AggDedupDecision, DedupDecisionKind

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
    await session.execute(delete(AggDedupDecision).where(
        AggDedupDecision.item_a_id == raw_item_id,
    ))

    exact = await service.find_exact_duplicate(normalized_text, raw_item_id) if normalized_text.strip() else None
    media_overlap_ids = await service.find_media_sha_overlap(media_file_ids, raw_item_id)
    if exact is not None and (len(normalized_text.strip()) >= 20 or exact.id in media_overlap_ids):
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
    best = next((c for c in candidates
                 if c.similarity >= _HIGH_TEXT_SIMILARITY_FOR_AUTO
                 and c.raw_item_id in media_overlap_ids), None)
    if best is not None:
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

    if exact is not None or media_overlap_ids:
        for candidate_id in set(media_overlap_ids + ([exact.id] if exact is not None else [])):
            await service.record_decision(
                raw_item_id, candidate_id, level=3,
                decision=DedupDecisionKind.UNCERTAIN,
                reason="совпадение медиа или короткого текста требует проверки",
                features={"media_overlap": media_overlap_ids},
            )
    needs_review = bool(candidates or exact is not None or media_overlap_ids)
    return DedupOutcome(False, None, needs_review, "uncertain_candidates" if needs_review else "no_candidates")
