"""Дедупликация между публикациями разных источников.

Уровни (см. ТЗ, раздел 11):
1. Явная пересылка/ссылка на оригинал.
2. Точный хеш нормализованного текста.
3. Совпадение медиа (sha256 файлов).
4. Похожий текст (pg_trgm) + доп. признаки (место, дата, набор фото).
5. DeepSeek для спорных пар (не реализован в этой версии — попадает в review).

Кандидаты отбираются средствами БД (pg_trgm + временное окно), не полным
перебором через LLM. Слабые совпадения A-B и B-C не объединяют кластер
автоматически: каждое решение — отдельная запись agg_dedup_decisions.
"""

from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import (
    AggContentVersion,
    AggDedupDecision,
    AggRawItem,
    DedupDecisionKind,
)

ALGORITHM_VERSION = "v1"
_CANDIDATE_WINDOW_DAYS = 14
_TRGM_SIMILARITY_THRESHOLD = 0.5
_MAX_CANDIDATES = 20


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
        self, content_hash_value: str, exclude_raw_item_id: int
    ) -> AggRawItem | None:
        """Уровень 2: точный хеш нормализованного текста в окне времени."""
        result = await self._session.execute(
            select(AggRawItem)
            .join(AggContentVersion, AggContentVersion.raw_item_id == AggRawItem.id)
            .where(
                AggContentVersion.is_current.is_(True),
                AggRawItem.id != exclude_raw_item_id,
                AggRawItem.content_hash == content_hash_value,
                AggRawItem.post_id.is_not(None),
            )
            .order_by(AggRawItem.first_seen_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_text_candidates(
        self, normalized_text: str, exclude_raw_item_id: int, published_at
    ) -> list[DedupCandidate]:
        """Уровень 4: pg_trgm similarity на уже опубликованных постах в
        ограниченном временном окне — не полный перебор базы."""
        if not normalized_text or len(normalized_text) < 20:
            return []

        window_start = published_at - timedelta(days=_CANDIDATE_WINDOW_DAYS)
        window_end = published_at + timedelta(days=_CANDIDATE_WINDOW_DAYS)

        query = text(
            """
            SELECT r.id AS raw_item_id, cv.id AS content_version_id,
                   similarity(cv.normalized_text, :needle) AS sim
            FROM agg_content_versions cv
            JOIN agg_raw_items r ON r.id = cv.raw_item_id
            WHERE cv.is_current = true
              AND r.id != :exclude_id
              AND r.post_id IS NOT NULL
              AND r.first_seen_at BETWEEN :window_start AND :window_end
              AND similarity(cv.normalized_text, :needle) > :threshold
            ORDER BY sim DESC
            LIMIT :limit
            """
        )
        rows = await self._session.execute(
            query,
            {
                "needle": normalized_text,
                "exclude_id": exclude_raw_item_id,
                "window_start": window_start,
                "window_end": window_end,
                "threshold": _TRGM_SIMILARITY_THRESHOLD,
                "limit": _MAX_CANDIDATES,
            },
        )
        return [
            DedupCandidate(row.raw_item_id, row.content_version_id, row.sim)
            for row in rows
        ]

    async def find_media_sha_overlap(
        self, media_file_ids: list[int], exclude_raw_item_id: int
    ) -> list[int]:
        """Уровень 3: пересечение по sha256 медиафайлов (уже сведено к
        media_file_id на этапе загрузки). Одной общей фотографии недостаточно
        для решения — это только признак, финальное решение комбинирует его
        с текстовым сходством."""
        if not media_file_ids:
            return []
        query = text(
            """
            SELECT DISTINCT pm.post_id
            FROM post_media pm
            JOIN agg_raw_items r ON r.post_id = pm.post_id
            WHERE pm.media_file_id = ANY(:ids) AND r.id != :exclude_id
            """
        )
        rows = await self._session.execute(
            query, {"ids": media_file_ids, "exclude_id": exclude_raw_item_id}
        )
        return [row[0] for row in rows]

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
