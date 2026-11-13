
from datetime import timedelta

from sqlalchemy import exists, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import (
    AggContentVersion,
    AggDedupDecision,
    AggRawItem,
    AggMediaAttachment,
    AggProcessingTask,
    DedupDecisionKind,
)
from src.aggregator.normalize.text import normalize_for_hash

ALGORITHM_VERSION = "v2"
_CANDIDATE_WINDOW_DAYS = 14
_TRGM_SIMILARITY_THRESHOLD = 0.5
_MAX_CANDIDATES = 20


def _canonical_candidate():
    return or_(
        AggRawItem.post_id.is_not(None),
        exists().where(
            AggProcessingTask.raw_item_id == AggRawItem.id,
            AggProcessingTask.stage == "dedup",
            AggProcessingTask.status == "done",
        ) & ~exists().where(
            AggDedupDecision.item_a_id == AggRawItem.id,
            AggDedupDecision.decision == DedupDecisionKind.DUPLICATE.value,
        ),
    )


class DedupCandidate:
    __slots__ = ("raw_item_id", "content_version_id", "similarity")

    def __init__(self, raw_item_id: int, content_version_id: int, similarity: float):
        self.raw_item_id = raw_item_id
        self.content_version_id = content_version_id
        self.similarity = similarity


class DedupService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def find_exact_duplicate(
        self, normalized_text: str, exclude_raw_item_id: int
    ) -> AggRawItem | None:
        result = await self._session.execute(
            select(AggRawItem)
            .join(AggContentVersion, AggContentVersion.raw_item_id == AggRawItem.id)
            .where(
                AggContentVersion.is_current.is_(True),
                AggRawItem.id != exclude_raw_item_id,
                func.btrim(func.regexp_replace(
                    func.lower(func.normalize(AggContentVersion.normalized_text, literal_column("NFKC"))),
                    r"\s+", " ", "g",
                )) == normalize_for_hash(normalized_text),
                _canonical_candidate(),
            )
            .order_by(AggRawItem.first_seen_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_text_candidates(
        self, normalized_text: str, exclude_raw_item_id: int, published_at
    ) -> list[DedupCandidate]:
        if not normalized_text or len(normalized_text) < 20:
            return []

        window_start = published_at - timedelta(days=_CANDIDATE_WINDOW_DAYS)
        window_end = published_at + timedelta(days=_CANDIDATE_WINDOW_DAYS)

        similarity = func.similarity(AggContentVersion.normalized_text, normalized_text)
        rows = await self._session.execute(
            select(AggRawItem.id, AggContentVersion.id, similarity)
            .join(AggContentVersion, AggContentVersion.raw_item_id == AggRawItem.id)
            .where(
                AggContentVersion.is_current.is_(True),
                AggRawItem.id != exclude_raw_item_id,
                _canonical_candidate(),
                AggRawItem.first_seen_at.between(window_start, window_end),
                similarity > _TRGM_SIMILARITY_THRESHOLD,
            )
            .order_by(similarity.desc(), AggRawItem.id)
            .limit(_MAX_CANDIDATES)
        )
        return [DedupCandidate(*row) for row in rows]

    async def find_media_sha_overlap(
        self, media_file_ids: list[int], exclude_raw_item_id: int
    ) -> list[int]:
        if not media_file_ids:
            return []
        rows = await self._session.scalars(
            select(AggMediaAttachment.raw_item_id)
            .join(AggRawItem, AggRawItem.id == AggMediaAttachment.raw_item_id)
            .where(
                AggMediaAttachment.media_file_id.in_(media_file_ids),
                AggRawItem.id != exclude_raw_item_id,
                _canonical_candidate(),
            )
            .distinct()
        )
        return list(rows)

    async def record_decision(
        self,
        item_a_id: int,
        item_b_id: int,
        level: int,
        decision: DedupDecisionKind,
        reason: str,
        features: dict,
    ) -> AggDedupDecision:
        record = AggDedupDecision(
            item_a_id=item_a_id,
            item_b_id=item_b_id,
            level=level,
            decision=decision.value,
            reason=reason,
            features=features,
            algorithm_version=ALGORITHM_VERSION,
        )
        self._session.add(record)
        await self._session.flush()
        return record
