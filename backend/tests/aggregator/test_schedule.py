import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from src.aggregator import commands
from src.aggregator.repository import TaskRepository
from src.settings import settings


@pytest.fixture
def scheduler(monkeypatch):
    stats = {}

    @asynccontextmanager
    async def run(*args):
        yield stats

    monkeypatch.setattr(commands, "command_run", run)
    monkeypatch.setattr(commands.aggregator_settings, "TELEGRAM_API_ID", 123)
    monkeypatch.setattr(commands.aggregator_settings, "TELEGRAM_API_HASH", "test")
    monkeypatch.setattr(commands.llm_settings, "DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(settings, "S3_BUCKET", "test")
    monkeypatch.setattr(settings, "S3_ACCESS_KEY_ID", "test")
    monkeypatch.setattr(settings, "S3_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(commands, "_run_telegram_sync", AsyncMock(return_value={"test": {"created": 1}}))
    monkeypatch.setattr(commands, "_run_farpost_sync", AsyncMock())
    monkeypatch.setattr(commands, "_drain_pipeline", AsyncMock(return_value={"publish": {"done": 1}}))
    return stats


@pytest.mark.parametrize("sync_due", [True, False])
async def test_scheduler_collects_on_tick_and_retries_between_ticks(scheduler, sync_due):
    stats = await commands._scheduled_pass(sync_due=sync_due)
    assert commands._run_telegram_sync.await_count == int(sync_due)
    commands._run_farpost_sync.assert_not_awaited()
    commands._drain_pipeline.assert_awaited_once()
    assert stats["pipeline"]["publish"]["done"] == 1


async def test_missing_configuration_is_visible_without_consuming_task_attempts(scheduler, monkeypatch):
    monkeypatch.setattr(commands.aggregator_settings, "TELEGRAM_API_ID", None)
    stats = await commands._scheduled_pass(sync_due=True)
    assert "TELEGRAM_API_ID" in stats["error"]
    assert commands._has_errors(stats)
    commands._run_telegram_sync.assert_not_awaited()
    commands._drain_pipeline.assert_not_awaited()


async def test_schedule_runs_one_pass_at_a_time(scheduler, monkeypatch):
    @asynccontextmanager
    async def session():
        yield object()

    monkeypatch.setattr(commands, "async_session_maker", session)
    monkeypatch.setattr(TaskRepository, "has_ready", AsyncMock(return_value=True))
    calls = []
    active = 0

    async def run(*, sync_due):
        nonlocal active
        active += 1
        assert active == 1
        calls.append(sync_due)
        active -= 1

    async def sleep(seconds):
        assert seconds == 5
        if len(calls) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(commands, "_scheduled_pass", run)
    monkeypatch.setattr(commands.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await commands.cmd_schedule()
    assert calls == [True, False, False]
