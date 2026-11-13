
from datetime import date, datetime, timezone

import pytest
from src.aggregator.writer.posts import PostWriter
from src.models.post import PostKind, PostStatus, Source


@pytest.mark.asyncio
async def test_incident_post_has_no_fishing_date(session):
    source = Source(type="telegram", name="t", external_id="1")
    session.add(source)
    await session.flush()

    writer = PostWriter(session)
    post = await writer.upsert_post(
        existing_post_id=None,
        source_id=source.id,
        external_post_id="e1",
        original_url=None,
        text="На льду бухты провалились двое рыбаков, спасены МЧС",
        published_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
        kind=PostKind.INCIDENT,
        status=PostStatus.PUBLISHED,
        fishing_date=None,
        event_date=date(2026, 11, 13),
        spot_id=None,
        method_id=None,
        bait=None,
        conditions=None,
        tg_reactions_count=None,
        tg_comments_count=None,
    )

    assert post.kind == PostKind.INCIDENT.value
    assert post.fishing_date is None, "происшествие не должно получать дату рыбалки"
    assert post.event_date == date(2026, 11, 13)


@pytest.mark.asyncio
async def test_reimport_preserves_manually_moderated_fields(session):
    source = Source(type="telegram", name="t", external_id="2")
    session.add(source)
    await session.flush()

    writer = PostWriter(session)
    post = await writer.upsert_post(
        existing_post_id=None, source_id=source.id, external_post_id="e2",
        original_url=None, text="исходный текст", published_at=datetime.now(timezone.utc),
        kind=PostKind.FISHING_REPORT, status=PostStatus.PUBLISHED,
        fishing_date=None, event_date=None, spot_id=None, method_id=None,
        bait=None, conditions=None, tg_reactions_count=None, tg_comments_count=None,
    )

    post.status = PostStatus.HIDDEN.value
    post.managed_fields = {"status": True}
    await session.flush()

    updated = await writer.upsert_post(
        existing_post_id=post.id, source_id=source.id, external_post_id="e2",
        original_url=None, text="отредактированный источником текст",
        published_at=datetime.now(timezone.utc),
        kind=PostKind.FISHING_REPORT, status=PostStatus.PUBLISHED,
        fishing_date=None, event_date=None, spot_id=None, method_id=None,
        bait=None, conditions=None, tg_reactions_count=None, tg_comments_count=None,
    )

    assert updated.status == PostStatus.HIDDEN.value, (
        "повторный импорт не должен отменять ручное скрытие публикации модератором"
    )
    assert updated.text == "отредактированный источником текст", (
        "поля, не зафиксированные модератором, источник всё ещё обновляет"
    )
