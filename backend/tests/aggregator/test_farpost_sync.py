import asyncio
import json
from datetime import datetime, timedelta, timezone
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select, update

from src.aggregator.config import aggregator_settings
from src.aggregator.models import AggProcessingTask
from src.aggregator.pipeline.publish_stage import process_publish_tasks
from src.aggregator.repository import CursorRepository
from src.aggregator.sources.farpost_collector import FarpostCollector, FarpostHttpError, ListingDetail, ListingSummary
from src.aggregator.sources.farpost_import import import_listings
from src.aggregator.sources.farpost_sync import _resolve_city_id, sync_farpost
from src.city.models import City
from src.models.listing import Listing, ListingPriceHistory


@pytest.fixture(autouse=True)
async def isolate_queue(session):
    await session.execute(update(AggProcessingTask).values(
        available_at=datetime.now(timezone.utc) + timedelta(days=365),
    ))


def summary(item_id):
    return ListingSummary(str(item_id), "test", f"https://www.farpost.ru/vladivostok/test-{item_id}.html")


def detail(url, item_id):
    return ListingDetail(str(item_id), "test", url, None, 100, "100", [], None, None)


async def test_real_delay_applies_to_every_request_and_redirect():
    times = []

    def response(request):
        times.append(monotonic())
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/finish"})
        return httpx.Response(200, text="нет объявлений")

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        collector = FarpostCollector(client, "https://www.farpost.ru", "vladivostok", delay=.02)
        await asyncio.gather(collector._get("https://www.farpost.ru/start"), collector._get("https://www.farpost.ru/other"))
    assert len(times) == 3
    assert all(b - a >= .019 for a, b in zip(times, times[1:]))


@pytest.mark.parametrize("status,html", [(403, "blocked"), (429, "limited"), (200, '<title>Captcha</title>')])
async def test_restrictions_stop_collector(status, html):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, text=html))) as client:
        collector = FarpostCollector(client, "https://www.farpost.ru", "vladivostok", delay=0)
        with pytest.raises(FarpostHttpError) as raised:
            await collector.fetch_list_page(1)
    assert raised.value.stops_run


async def test_unknown_markup_is_visible_instead_of_empty_success():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<html>Changed layout</html>"))) as client:
        with pytest.raises(FarpostHttpError, match="import-listings"):
            await FarpostCollector(client, "https://www.farpost.ru", "vladivostok", delay=0).fetch_list_page(1)


async def test_detail_limit_stops_entire_run_and_keeps_history_cursor(session):
    await CursorRepository(session).set("farpost", "incremental", {"next_page": 8})
    collector = SimpleNamespace(
        fetch_list_page=AsyncMock(return_value=[summary(1), summary(2)]),
        fetch_detail=AsyncMock(side_effect=FarpostHttpError(429, "https://www.farpost.ru")),
    )
    stats = await sync_farpost(session, collector, max_pages=3, max_listings=None, city_path="vladivostok/sport/fish/")
    assert stats["errors"] == 1 and stats["manual_import"]
    collector.fetch_detail.assert_awaited_once()
    assert (await CursorRepository(session).get("farpost", "incremental"))["next_page"] == 8


async def test_rechecks_fresh_pages_then_continues_history_without_duplicates(session, monkeypatch):
    monkeypatch.setattr(aggregator_settings, "FARPOST_RECHECK_PAGES", 2)
    await CursorRepository(session).set("farpost", "incremental", {"next_page": 8})
    collector = SimpleNamespace(
        fetch_list_page=AsyncMock(side_effect=lambda page: [summary(f"fresh-{page}")]),
        fetch_detail=AsyncMock(side_effect=detail),
    )
    first = await sync_farpost(session, collector, max_pages=3, max_listings=None, city_path="vladivostok/sport/fish/")
    assert [call.args[0] for call in collector.fetch_list_page.await_args_list] == [1, 2, 8]
    assert first["created"] == 3
    assert (await CursorRepository(session).get("farpost", "incremental"))["next_page"] == 9
    second = await sync_farpost(session, collector, max_pages=1, max_listings=None, city_path="vladivostok/sport/fish/")
    assert second["unchanged"] == 1 and second["created"] == 0


async def test_city_slug_and_explicit_locality_do_not_guess_first_city(session):
    city = City(name="Находка", lat=0, lon=0, timezone="Asia/Vladivostok")
    session.add(city)
    await session.flush()
    assert await _resolve_city_id(session, "nakhodka/sport/fish/") == city.id
    assert await _resolve_city_id(session, "vladivostok/sport/fish/", "Находка") == city.id
    assert await _resolve_city_id(session, "unknown/sport/fish/") is None


async def test_manual_json_csv_is_idempotent_and_bad_row_does_not_rollback_good_one(session, tmp_path):
    path = tmp_path / "listings.json"
    valid = {"farpost_id": "manual-test", "title": "Катушка", "url": "https://www.farpost.ru/vladivostok/reel-123.html", "price_rub": 3000}
    path.write_text(json.dumps([valid, {**valid, "farpost_id": "invalid", "price_rub": -1}]), encoding="utf-8")
    first = await import_listings(session, path)
    assert first["created"] == 1 and first["errors"] == 1
    assert await process_publish_tasks(session, 10) == {"done": 1, "failed": 0}
    post = await session.scalar(select(Listing).where(Listing.farpost_id == "manual-test"))
    original_id = post.id
    csv_path = tmp_path / "listings.csv"
    csv_path.write_text("farpost_id,title,url,price_rub\nmanual-test,Катушка,https://www.farpost.ru/vladivostok/reel-123.html,2800\n", encoding="utf-8")
    assert (await import_listings(session, csv_path))["updated"] == 1
    assert await process_publish_tasks(session, 10) == {"done": 1, "failed": 0}
    assert (await import_listings(session, csv_path))["unchanged"] == 1
    assert post.id == original_id and post.price_rub == 2800
    assert len(list(await session.scalars(select(ListingPriceHistory).where(ListingPriceHistory.listing_id == post.id)))) == 2
