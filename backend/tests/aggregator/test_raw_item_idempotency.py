
import pytest
from src.aggregator.repository import RawItemRepository


@pytest.mark.asyncio
async def test_repeated_import_does_not_duplicate(session):
    repo = RawItemRepository(session)

    item1, changed1, is_new1 = await repo.upsert_raw_item(
        kind="telegram_post",
        source_key="telegram:999",
        external_id="42",
        raw_payload={"text": "Отчёт о рыбалке"},
        content_hash="hash-a",
        parser_version="v1",
    )
    assert is_new1 is True
    assert changed1 is True

    item2, changed2, is_new2 = await repo.upsert_raw_item(
        kind="telegram_post",
        source_key="telegram:999",
        external_id="42",
        raw_payload={"text": "Отчёт о рыбалке"},
        content_hash="hash-a",
        parser_version="v1",
    )
    assert item2.id == item1.id
    assert is_new2 is False
    assert changed2 is False, "повторный импорт того же содержимого не должен считаться изменением"


@pytest.mark.asyncio
async def test_edited_post_updates_same_entity(session):
    repo = RawItemRepository(session)

    item1, _, _ = await repo.upsert_raw_item(
        kind="telegram_post",
        source_key="telegram:999",
        external_id="43",
        raw_payload={"text": "Старый текст"},
        content_hash="hash-old",
        parser_version="v1",
    )

    item2, changed, is_new = await repo.upsert_raw_item(
        kind="telegram_post",
        source_key="telegram:999",
        external_id="43",
        raw_payload={"text": "Новый текст после редактирования"},
        content_hash="hash-new",
        parser_version="v1",
    )

    assert item2.id == item1.id, "та же внешняя публикация должна обновлять ту же сущность"
    assert is_new is False
    assert changed is True
    assert item2.content_hash == "hash-new"
    assert item2.raw_payload["text"] == "Новый текст после редактирования"
