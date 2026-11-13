from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import httpx
import pytest
from src.app import app
from src.aggregator.deps import get_farpost_service
from src.aggregator.service import FarpostService
from src.aggregator.sources.farpost_collector import FarpostHttpError, ListingDetail, ListingSummary


def summary(item_id):
    return ListingSummary(item_id, f"Катушка {item_id}", f"https://www.farpost.ru/{item_id}.html")


def detail(url, farpost_id):
    return ListingDetail(
        farpost_id=farpost_id, title=f"Катушка {farpost_id}", url=url,
        description="Описание товара", price_rub=3000, price_raw="3 000 ₽",
        photo_urls=["https://example.org/photo.jpg"],
        seller_name="Продавец", seller_url="https://www.farpost.ru/user/test/",
        characteristics={"Состояние": "Новое"}, category_breadcrumb="Катушки",
    )


@pytest.fixture
def collector():
    return SimpleNamespace(
        fetch_list_page=AsyncMock(return_value=[]), fetch_detail=AsyncMock(side_effect=detail),
    )


@pytest.fixture
async def api(collector):
    app.dependency_overrides[get_farpost_service] = lambda: FarpostService(collector)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_farpost_service)


@pytest.mark.asyncio
async def test_limit_paginates_and_returns_full_unique_cards(api, collector):
    collector.fetch_list_page.side_effect = [[summary("1"), summary("2")], [summary("2"), summary("3"), summary("4")]]
    response = await api.get("/aggregator/farpost", params={"limit": 3})
    assert response.status_code == 200
    data = response.json()
    assert [item["farpost_id"] for item in data] == ["1", "2", "3"]
    assert data[0]["price_rub"] == 3000
    assert data[0]["description"] == "Описание товара"
    assert data[0]["photo_urls"] == ["https://example.org/photo.jpg"]
    assert data[0]["seller_name"] == "Продавец"
    assert data[0]["characteristics"] == {"Состояние": "Новое"}
    assert collector.fetch_list_page.await_args_list == [call(1), call(2)]
    assert collector.fetch_detail.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("last_page", [[], [summary("1")]])
async def test_short_or_repeated_catalog_stops(api, collector, last_page):
    collector.fetch_list_page.side_effect = [[summary("1")], last_page]
    response = await api.get("/aggregator/farpost", params={"limit": 5})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert collector.fetch_detail.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 51, "abc"])
async def test_invalid_limit_is_rejected_before_fetch(api, collector, limit):
    response = await api.get("/aggregator/farpost", params={"limit": limit})
    assert response.status_code == 422
    collector.fetch_list_page.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    FarpostHttpError(403, "https://www.farpost.ru/"),
    httpx.ReadTimeout("timeout"), httpx.ConnectError("connection failed"),
])
async def test_upstream_error_has_readable_response(api, collector, error):
    collector.fetch_list_page.side_effect = error
    response = await api.get("/aggregator/farpost", params={"limit": 1})
    assert response.status_code == 502
    assert "Farpost" in response.json()["detail"]


@pytest.mark.asyncio
async def test_swagger_exposes_limit_and_card_fields(api):
    schema = (await api.get("/openapi.json")).json()
    operation = schema["paths"]["/aggregator/farpost"]["get"]
    limit = operation["parameters"][0]["schema"]
    assert (limit["minimum"], limit["maximum"], limit["default"]) == (1, 50, 5)
    assert "photo_urls" in schema["components"]["schemas"]["ListingDetail"]["properties"]
