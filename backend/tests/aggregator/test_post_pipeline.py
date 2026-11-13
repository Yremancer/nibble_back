from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update

from src.aggregator.config import NormalizationRule
from src.aggregator.dedup.pipeline import resolve_duplicate
from src.aggregator.dedup.service import DedupCandidate, DedupService
from src.aggregator.models import AggDedupDecision, AggProcessingTask, AggRawItem, ProcessingStage
from src.aggregator.pipeline.classify import process_classify_tasks
from src.aggregator.pipeline.dedup_stage import process_dedup_tasks
from src.aggregator.pipeline.ingest import ingest_telegram_post
from src.aggregator.pipeline.media_stage import process_media_tasks
from src.aggregator.pipeline.publish_stage import process_publish_tasks
from src.aggregator.pipeline.resolve import process_resolve_tasks
from src.aggregator.repository import ClassificationRepository, RawItemRepository, TaskRepository
from src.llm.settings import llm_settings
from src.models.media import PostMedia
from src.post.models import Post, PostSpecies, Source
from src.storage.models import File


@pytest.fixture(autouse=True)
async def isolate_queue(session):
    await session.execute(update(AggProcessingTask).values(
        available_at=datetime.now(timezone.utc) + timedelta(days=365),
    ))


async def source(session, name):
    value = Source(type="telegram", name=name, external_id=name)
    session.add(value)
    await session.flush()
    return value


async def ingest(session, src, text, *, result=None, refs=(), published_at=None, url=None):
    item_id, _, _ = await ingest_telegram_post(
        session, source_key=f"telegram:{src.id}", external_id="1",
        raw_payload={"source_id": src.id, "external_post_id": "1",
                     "published_at": (published_at or datetime(2026, 11, 13, tzinfo=timezone.utc)).isoformat(),
                     "original_url": url},
        raw_text=text, media_refs=list(refs),
        boilerplate_rules=[NormalizationRule(pattern=r"\nПодписывайтесь.*$")], parser_version="test",
    )
    version = await RawItemRepository(session).get_current_content_version(item_id)
    await ClassificationRepository(session).store(
        version.id, model=llm_settings.DEEPSEEK_MODEL, prompt_version=llm_settings.PROMPT_VERSION,
        decision="keep", result=result or {"decision": "keep", "category": "useful_info", "reason": "test"},
        tokens_in=None, tokens_out=None, cost_estimate_usd=None,
    )
    return await session.get(AggRawItem, item_id)


async def pipeline(session, media=None):
    await process_classify_tasks(session, AsyncMock(), llm_settings, 200)
    await process_resolve_tasks(session, 200)
    await process_media_tasks(session, media or AsyncMock(), 200)
    dedup = await process_dedup_tasks(session, 200)
    publish = await process_publish_tasks(session, 200)
    return dedup, publish


@pytest.mark.asyncio
async def test_same_batch_two_channels_use_cleaned_text_and_publish_once(session):
    src_a, src_b = await source(session, "batch-a"), await source(session, "batch-b")
    text = "В бухте сегодня поймали несколько крупных рыб и вернулись домой"
    a = await ingest(session, src_a, text + "\nПодписывайтесь на первый канал")
    b = await ingest(session, src_b, text.upper() + "\nПодписывайтесь на второй канал")
    assert a.content_hash != b.content_hash
    dedup, publish = await pipeline(session)
    assert dedup == {"done": 1, "failed": 0, "duplicates": 1}
    assert publish == {"done": 1, "failed": 0}
    assert a.post_id is not None and b.post_id is None
    await pipeline(session)
    posts = list(await session.scalars(select(Post).where(Post.source_id.in_([src_a.id, src_b.id]))))
    assert len(posts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_queue", [False, True])
async def test_similar_text_uses_uploaded_media_in_same_batch(session, legacy_queue):
    src_a, src_b = await source(session, "media-a"), await source(session, "media-b")
    text = "Сегодня была отличная рыбалка, поймали много наваги и терпуга на донную снасть в бухте Аякс"
    a = await ingest(session, src_a, text, refs=[("https://example.org/a.jpg", "photo")])
    b = await ingest(session, src_b, text + "!", refs=[("https://example.org/b.jpg", "photo")])
    if legacy_queue:
        await session.execute(update(AggProcessingTask).where(
            AggProcessingTask.raw_item_id.in_([a.id, b.id]),
        ).values(status="done"))
        repo = TaskRepository(session)
        for item in (a, b):
            await repo.enqueue(item.id, ProcessingStage.DEDUP)
        await repo.enqueue_missing_media()
    file = File(key="image/pipeline-shared.jpg", original_name="test", content_type="image/jpeg", size=4)
    session.add(file)
    await session.flush()
    media = SimpleNamespace(store_from_url=AsyncMock(return_value=file))
    dedup, publish = await pipeline(session, media)
    assert media.store_from_url.await_count == 2
    assert dedup == {"done": 1, "failed": 0, "duplicates": 1}
    assert publish == {"done": 1, "failed": 0}
    assert a.post_id is not None and b.post_id is None


@pytest.mark.asyncio
async def test_uncertain_match_goes_to_moderation_and_stale_decisions_clear(session):
    src_a, src_b = await source(session, "review-a"), await source(session, "review-b")
    text = "Сегодня была отличная рыбалка, поймали много наваги и терпуга на донную снасть в бухте Аякс"
    await ingest(session, src_a, text)
    b = await ingest(session, src_b, text + "!")
    await pipeline(session)
    post = await session.get(Post, b.post_id)
    assert post.status == "moderation"
    original_post_id = post.id
    await ingest(session, src_b, "Совсем другая публикация: расписание городского автобуса изменилось")
    await pipeline(session)
    assert b.post_id == original_post_id
    assert post.status == "published"
    assert list(await session.scalars(select(AggDedupDecision).where(AggDedupDecision.item_a_id == b.id))) == []


@pytest.mark.asyncio
async def test_identical_short_text_requires_moderation(session):
    src_a, src_b = await source(session, "short-a"), await source(session, "short-b")
    await ingest(session, src_a, "Клюёт")
    b = await ingest(session, src_b, "Клюёт")
    dedup, publish = await pipeline(session)
    assert dedup["duplicates"] == 0 and publish["done"] == 2
    assert (await session.get(Post, b.post_id)).status == "moderation"


@pytest.mark.asyncio
async def test_one_common_photo_without_text_requires_moderation(session):
    src_a, src_b = await source(session, "photo-only-a"), await source(session, "photo-only-b")
    await ingest(session, src_a, "", refs=[("https://example.org/photo-only-a.jpg", "photo")])
    b = await ingest(session, src_b, "", refs=[("https://example.org/photo-only-b.jpg", "photo")])
    file = File(key="image/photo-only.jpg", original_name="test", content_type="image/jpeg", size=4)
    session.add(file)
    await session.flush()
    dedup, publish = await pipeline(session, SimpleNamespace(store_from_url=AsyncMock(return_value=file)))
    assert dedup["duplicates"] == 0 and publish["done"] == 2
    assert (await session.get(Post, b.post_id)).status == "moderation"


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [False, True])
async def test_source_edit_updates_same_post_clears_fields_and_preserves_moderator(session, managed):
    src = await source(session, "edit-fields")
    initial_time = datetime(2026, 11, 12, tzinfo=timezone.utc)
    classification = {
        "decision": "keep", "category": "fishing_report", "reason": "test",
        "species": [{"name": "Навага", "evidence": "навага", "quantity": 2}],
        "methods": [{"name": "Спиннинг", "evidence": "спиннинг"}],
        "location_mentions": [{"text": "Бухта Аякс", "evidence": "Аякс"}],
        "bait": "червь", "conditions": "ветер",
    }
    item = await ingest(session, src, "Поймали навагу в бухте Аякс на спиннинг", result=classification,
                        refs=[("https://example.org/edit.jpg", "photo")], published_at=initial_time, url="https://t.me/edit/1")
    file = File(key="image/pipeline-edit.jpg", original_name="test", content_type="image/jpeg", size=4)
    session.add(file)
    await session.flush()
    await pipeline(session, SimpleNamespace(store_from_url=AsyncMock(return_value=file)))
    post = await session.get(Post, item.post_id)
    original_id = post.id
    assert len(list(await session.scalars(select(PostSpecies).where(PostSpecies.post_id == post.id)))) == 1
    if managed:
        post.text = "Ручной текст"
        post.status = "hidden"
        post.managed_fields = {field: True for field in (
            "text", "status", "media", "catches", "published_at", "original_url", "bait",
        )}
        await session.flush()
    new_time = initial_time + timedelta(days=1)
    await ingest(session, src, "Теперь это полезная информация без рыбы и фотографий", published_at=new_time)
    await pipeline(session)
    assert item.post_id == original_id
    assert post.kind == "useful_info"
    assert post.spot_id is None and post.method_id is None
    assert post.conditions is None and post.fishing_date is None
    catches = list(await session.scalars(select(PostSpecies).where(PostSpecies.post_id == post.id)))
    media = list(await session.scalars(select(PostMedia).where(PostMedia.post_id == post.id)))
    assert len(catches) == len(media) == int(managed)
    assert post.text == ("Ручной текст" if managed else "Теперь это полезная информация без рыбы и фотографий")
    assert post.status == ("hidden" if managed else "published")
    assert post.bait == ("червь" if managed else None)
    assert post.original_url == ("https://t.me/edit/1" if managed else None)
    assert post.published_at == (initial_time if managed else new_time)


@pytest.mark.asyncio
async def test_media_overlap_must_belong_to_chosen_text_candidate(session, monkeypatch):
    src = await source(session, "candidate-media")
    a = await ingest(session, src, "первый")
    src_b = await source(session, "candidate-media-b")
    b = await ingest(session, src_b, "второй")
    src_c = await source(session, "candidate-media-c")
    c = await ingest(session, src_c, "третий")
    monkeypatch.setattr(DedupService, "find_exact_duplicate", AsyncMock(return_value=None))
    monkeypatch.setattr(DedupService, "find_text_candidates", AsyncMock(return_value=[
        DedupCandidate(a.id, 1, .99), DedupCandidate(b.id, 2, .90),
    ]))
    monkeypatch.setattr(DedupService, "find_media_sha_overlap", AsyncMock(return_value=[b.id]))
    outcome = await resolve_duplicate(session, c.id, "test", "похожий текст", c.first_seen_at, [1])
    assert outcome.is_duplicate and outcome.canonical_raw_item_id == b.id
