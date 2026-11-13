
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from src.aggregator.dedup.pipeline import resolve_duplicate
from src.aggregator.models import AggDedupDecision, DedupDecisionKind
from src.aggregator.repository import RawItemRepository
from src.post.models import Post, Source


async def _make_post(session, external_id: str) -> Post:
    source = Source(type="telegram", name="t", external_id=f"src-{external_id}")
    session.add(source)
    await session.flush()
    post = Post(source_id=source.id, external_post_id=external_id, text="x")
    session.add(post)
    await session.flush()
    return post


async def _add_content_version(session, raw_item_id: int, normalized_text: str) -> None:
    repo = RawItemRepository(session)
    await repo.add_content_version(
        raw_item_id,
        original_text=normalized_text,
        normalized_text=normalized_text,
        removed_boilerplate=None,
        normalization_version="v1",
    )


@pytest.mark.asyncio
async def test_exact_text_hash_marks_duplicate(session):
    repo = RawItemRepository(session)
    original, _, _ = await repo.upsert_raw_item(
        kind="telegram_post", source_key="telegram:1", external_id="1",
        raw_payload={"text": "отчёт"}, content_hash="same-hash", parser_version="v1",
    )
    post = await _make_post(session, "post-a")
    original.post_id = post.id
    await session.flush()
    await _add_content_version(session, original.id, "Сегодня поймали много рыбы в бухте")

    new_item, _, _ = await repo.upsert_raw_item(
        kind="telegram_post", source_key="telegram:2", external_id="1",
        raw_payload={"text": "отчёт (пересланный)"}, content_hash="same-hash",
        parser_version="v1",
    )

    outcome = await resolve_duplicate(
        session, new_item.id, "same-hash", "Сегодня поймали много рыбы в бухте", datetime.now(timezone.utc), []
    )

    assert outcome.is_duplicate is True
    assert outcome.canonical_raw_item_id == original.id


@pytest.mark.asyncio
async def test_short_common_text_alone_is_not_enough(session):
    repo = RawItemRepository(session)
    other, _, _ = await repo.upsert_raw_item(
        kind="telegram_post", source_key="telegram:1", external_id="10",
        raw_payload={"text": "клюёт"}, content_hash="hash-x", parser_version="v1",
    )
    post = await _make_post(session, "post-b")
    other.post_id = post.id
    await session.flush()

    new_item, _, _ = await repo.upsert_raw_item(
        kind="telegram_post", source_key="telegram:2", external_id="10",
        raw_payload={"text": "клюёт"}, content_hash="hash-y", parser_version="v1",
    )

    outcome = await resolve_duplicate(
        session, new_item.id, "hash-y", "клюёт", datetime.now(timezone.utc), []
    )

    assert outcome.is_duplicate is False
    assert outcome.needs_review is False


@pytest.mark.asyncio
async def test_uncertain_candidates_recorded_not_auto_merged(session):
    repo = RawItemRepository(session)
    text_a = "Сегодня отличная рыбалка на Русском острове у бухты, поймал терпуга хорошего размера"
    item_a, _, _ = await repo.upsert_raw_item(
        kind="telegram_post", source_key="telegram:1", external_id="20",
        raw_payload={"text": text_a}, content_hash="hash-a", parser_version="v1",
    )
    post = await _make_post(session, "post-c")
    item_a.post_id = post.id
    await session.flush()
    await _add_content_version(session, item_a.id, text_a)

    text_b = "Сегодня отличная рыбалка на Русском острове у бухты, поймал терпуга среднего размера"
    item_b, _, _ = await repo.upsert_raw_item(
        kind="telegram_post", source_key="telegram:2", external_id="20",
        raw_payload={"text": text_b}, content_hash="hash-b", parser_version="v1",
    )

    outcome = await resolve_duplicate(
        session, item_b.id, "hash-b", text_b, datetime.now(timezone.utc), []
    )

    assert outcome.is_duplicate is False
    assert outcome.needs_review is True

    decisions = (
        await session.execute(select(AggDedupDecision).where(AggDedupDecision.item_a_id == item_b.id))
    ).scalars().all()
    assert len(decisions) >= 1
    assert decisions[0].decision == DedupDecisionKind.UNCERTAIN.value
