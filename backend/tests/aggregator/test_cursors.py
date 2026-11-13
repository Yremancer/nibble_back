
import pytest
from src.aggregator.repository import CursorRepository


@pytest.mark.asyncio
async def test_cursor_persists_and_is_separate_by_type(session):
    repo = CursorRepository(session)

    assert await repo.get("telegram:1", "incremental") is None

    await repo.set("telegram:1", "incremental", {"last_message_id": 100})
    await repo.set("telegram:1", "backfill", {"last_message_id": 5})

    incremental = await repo.get("telegram:1", "incremental")
    backfill = await repo.get("telegram:1", "backfill")

    assert incremental == {"last_message_id": 100}
    assert backfill == {"last_message_id": 5}, (
        "курсор истории и курсор новых сообщений должны храниться раздельно"
    )


@pytest.mark.asyncio
async def test_cursor_resumes_from_checkpoint_after_restart(session):
    repo = CursorRepository(session)

    await repo.set("farpost", "incremental", {"next_page": 7})

    resumed = await repo.get("farpost", "incremental")
    assert resumed["next_page"] == 7, "обход должен продолжиться со страницы 7, а не начаться заново"
