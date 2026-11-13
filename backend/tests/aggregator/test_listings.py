"""Сценарии 16, 17, 18: два разных объявления одного товара не склеиваются
(разные farpost_id), объявление не дублируется при повторной карточке
(обновление по точному farpost_id), 403/отсутствие не деактивируют карточку
молча (state=unknown не трогает is_active)."""

import pytest
from sqlalchemy import select
from src.aggregator.writer.listings import ListingWriter
from src.models.listing import Listing, ListingState


@pytest.mark.asyncio
async def test_same_product_different_sellers_are_distinct_listings(session):
    writer = ListingWriter(session)

    listing_a, created_a = await writer.upsert(
        farpost_id="111", category_id=None, city_id=None,
        title="Удилище Shimano", description=None, price_rub=5000, price_raw="5000",
        photo_url=None, url="https://farpost.ru/a.html", seller_name="Продавец А",
        seller_url=None, characteristics=None, state=ListingState.ACTIVE,
    )
    listing_b, created_b = await writer.upsert(
        farpost_id="222", category_id=None, city_id=None,
        title="Удилище Shimano", description=None, price_rub=5200, price_raw="5200",
        photo_url=None, url="https://farpost.ru/b.html", seller_name="Продавец Б",
        seller_url=None, characteristics=None, state=ListingState.ACTIVE,
    )

    assert created_a and created_b
    assert listing_a.id != listing_b.id


@pytest.mark.asyncio
async def test_exact_farpost_id_match_is_update_not_duplicate(session):
    writer = ListingWriter(session)

    listing1, created1 = await writer.upsert(
        farpost_id="333", category_id=None, city_id=None,
        title="Катушка", description=None, price_rub=3000, price_raw="3000",
        photo_url=None, url="https://farpost.ru/c.html", seller_name=None,
        seller_url=None, characteristics=None, state=ListingState.ACTIVE,
    )
    listing2, created2 = await writer.upsert(
        farpost_id="333", category_id=None, city_id=None,
        title="Катушка (обновлено)", description=None, price_rub=2800, price_raw="2800",
        photo_url=None, url="https://farpost.ru/c.html", seller_name=None,
        seller_url=None, characteristics=None, state=ListingState.ACTIVE,
    )

    assert created1 is True
    assert created2 is False
    assert listing1.id == listing2.id

    result = await session.execute(select(Listing).where(Listing.farpost_id == "333"))
    assert len(result.scalars().all()) == 1
    assert listing2.price_rub == 2800


@pytest.mark.asyncio
async def test_unknown_state_does_not_deactivate_listing(session):
    writer = ListingWriter(session)

    listing, _ = await writer.upsert(
        farpost_id="444", category_id=None, city_id=None,
        title="Эхолот", description=None, price_rub=15000, price_raw="15000",
        photo_url=None, url="https://farpost.ru/d.html", seller_name=None,
        seller_url=None, characteristics=None, state=ListingState.ACTIVE,
    )
    assert listing.is_active is True

    listing2, _ = await writer.upsert(
        farpost_id="444", category_id=None, city_id=None,
        title="Эхолот", description=None, price_rub=15000, price_raw="15000",
        photo_url=None, url="https://farpost.ru/d.html", seller_name=None,
        seller_url=None, characteristics=None, state=ListingState.UNKNOWN,
    )

    assert listing2.is_active is True, (
        "403/отсутствие в обходе (state=unknown) не должно молча снимать объявление"
    )
