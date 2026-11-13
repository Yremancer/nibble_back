import os
import select
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select as sa_select, text, update

from src.aggregator.models import AggProcessingTask, ProcessingStage
from src.aggregator.repository import RawItemRepository, TaskRepository
from src.settings import settings


def test_451_tasks_survive_process_kill_and_restart(migration_db):
    command.upgrade(Config("alembic.ini"), "head")
    migration_db.execute("""
        INSERT INTO agg_raw_items (kind, source_key, external_id, raw_payload, content_hash, parser_version)
        SELECT 'farpost_listing', 'restart-test', i::text,
               jsonb_build_object('farpost_id', i::text, 'title', 'test', 'url', 'https://example.org/' || i),
               i::text, 'test' FROM generate_series(1, 451) i;
        INSERT INTO agg_processing_tasks (raw_item_id, stage)
        SELECT id, 'publish' FROM agg_raw_items;
    """)
    env = {**os.environ, "DB_NAME": settings.DB_NAME}
    interrupted_script = """
import asyncio
from src.aggregator.commands import command_run
from src.aggregator.models import ProcessingStage
from src.aggregator.pipeline.publish_stage import process_publish_tasks
from src.database.database import async_session_maker

async def main():
    async with command_run('pipeline', 'test-restart') as stats:
        async with async_session_maker() as session:
            stats.update(await process_publish_tasks(session, 200))
            await session.commit()
        async with async_session_maker() as session:
            await process_publish_tasks(session, 200)
            print('uncommitted batch', flush=True)
            await asyncio.sleep(3600)
asyncio.run(main())
"""
    process = subprocess.Popen(
        [sys.executable, "-c", interrupted_script], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        ready, _, _ = select.select([process.stdout], [], [], 30)
        assert ready, "worker did not finish two batches in time"
        assert process.stdout.readline().strip() == "uncommitted batch"
    finally:
        process.kill()
        process.communicate(timeout=10)

    assert migration_db.execute("SELECT count(*) FROM listings").fetchone() == (200,)
    assert migration_db.execute("SELECT count(*) FROM agg_processing_tasks WHERE status = 'done'").fetchone() == (200,)
    assert migration_db.execute("SELECT count(*) FROM agg_processing_tasks WHERE status = 'in_progress'").fetchone() == (0,)

    resume_script = """
import asyncio
from src.aggregator.commands import command_run, _drain_stage
from src.aggregator.models import ProcessingStage

async def main():
    async with command_run('pipeline', 'test-restart') as stats:
        stats.update(await _drain_stage(ProcessingStage.PUBLISH, 200))
asyncio.run(main())
"""
    for _ in range(2):
        result = subprocess.run([sys.executable, "-c", resume_script], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert migration_db.execute("SELECT count(*), count(DISTINCT farpost_id) FROM listings").fetchone() == (451, 451)
        assert migration_db.execute("SELECT count(*) FROM agg_processing_tasks WHERE status = 'done'").fetchone() == (451,)
    runs = migration_db.execute("SELECT status, stats FROM agg_runs ORDER BY id").fetchall()
    assert [r[0] for r in runs] == ["failed", "success", "success"]
    assert runs[1][1] == {"done": 251, "failed": 0}
    assert runs[2][1] == {"done": 0, "failed": 0}
    result = subprocess.run([
        sys.executable, "-m", "src.aggregator.cli", "reprocess", "--stage", "publish", "--limit", "451",
    ], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert migration_db.execute("SELECT count(*) FROM listings").fetchone() == (451,)
    last_stats = migration_db.execute("SELECT stats FROM agg_runs ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert last_stats["requeued"] == 451
    assert last_stats["pipeline"]["publish"] == {"done": 451, "failed": 0}


def test_advisory_lock_rejects_overlapping_process_and_errors_are_journaled(migration_db):
    command.upgrade(Config("alembic.ini"), "head")
    env = {**os.environ, "DB_NAME": settings.DB_NAME}
    migration_db.execute("SELECT pg_advisory_lock(731912, 2)")
    try:
        result = subprocess.run([
            sys.executable, "-m", "src.aggregator.cli", "sync", "--source", "telegram", "--limit", "1",
        ], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode != 0 and "другая команда агрегатора" in result.stderr
        assert migration_db.execute("SELECT count(*) FROM agg_runs").fetchone() == (0,)
    finally:
        migration_db.execute("SELECT pg_advisory_unlock(731912, 2)")
    result = subprocess.run([
        sys.executable, "-m", "src.aggregator.cli", "reprocess", "--stage", "publish", "--limit", "0",
    ], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    status, error = migration_db.execute("SELECT status, error FROM agg_runs").fetchone()
    assert status == "failed" and "положительным" in error


@pytest.mark.asyncio
async def test_retry_delay_attempt_limit_manual_reset_and_old_claim(session):
    await session.execute(update(AggProcessingTask).values(available_at=datetime.now(timezone.utc) + timedelta(days=365)))
    item, _, _ = await RawItemRepository(session).upsert_raw_item(
        kind="telegram_post", source_key="retry-test", external_id="1",
        raw_payload={}, content_hash="retry-test", parser_version="test",
    )
    repo = TaskRepository(session)
    task = await repo.enqueue(item.id, ProcessingStage.PUBLISH)
    for attempt in range(1, 6):
        assert [t.id for t in await repo.claim_pending(ProcessingStage.PUBLISH, 10)] == [task.id]
        before = datetime.now(timezone.utc)
        await repo.mark_failed(task, "failure")
        assert task.attempts == attempt
        assert task.available_at >= before + timedelta(seconds=30 * 2 ** (attempt - 1))
        assert await repo.claim_pending(ProcessingStage.PUBLISH, 10) == []
        task.available_at = before
        await session.flush()
    assert await repo.claim_pending(ProcessingStage.PUBLISH, 10) == []
    assert [t.id for t in await repo.claim_failed(ProcessingStage.PUBLISH, 10)] == [task.id]
    assert task.attempts == 0
    task.status = "in_progress"
    await session.flush()
    assert [t.id for t in await repo.claim_pending(ProcessingStage.PUBLISH, 10)] == [task.id]


@pytest.mark.asyncio
async def test_database_error_in_one_listing_keeps_rest_of_batch(session, monkeypatch):
    from src.aggregator.pipeline.publish_stage import process_publish_tasks
    from src.aggregator.writer.listings import ListingWriter
    from src.models.listing import Listing

    await session.execute(update(AggProcessingTask).values(available_at=datetime.now(timezone.utc) + timedelta(days=365)))
    repo = TaskRepository(session)
    for external_id in ("bad-db-row", "good-db-row"):
        item, _, _ = await RawItemRepository(session).upsert_raw_item(
            kind="farpost_listing", source_key="isolation-test", external_id=external_id,
            raw_payload={"farpost_id": external_id, "title": "test", "url": "https://example.org"},
            content_hash=external_id, parser_version="test",
        )
        await repo.enqueue(item.id, ProcessingStage.PUBLISH)
    original = ListingWriter.upsert

    async def failing_upsert(self, **kwargs):
        result = await original(self, **kwargs)
        if kwargs["farpost_id"] == "bad-db-row":
            await session.execute(text("SELECT 1 / 0"))
        return result

    monkeypatch.setattr(ListingWriter, "upsert", failing_upsert)
    assert await process_publish_tasks(session, 200) == {"done": 1, "failed": 1}
    assert await session.scalar(sa_select(Listing.id).where(Listing.farpost_id == "good-db-row")) is not None
    assert await session.scalar(sa_select(Listing.id).where(Listing.farpost_id == "bad-db-row")) is None
