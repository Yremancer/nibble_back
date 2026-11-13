"""Сценарии 12 и 13: неизвестное место не получает выдуманные координаты
(остаётся кандидатом), вид рыбы сопоставляется со справочником по алиасам."""

import pytest
from sqlalchemy import insert
from src.aggregator.resolve.dictionary import DictionaryResolver
from src.models.geo import Spot
from src.models.species import Species


@pytest.mark.asyncio
async def test_species_resolved_by_alias(session):
    session.add(
        Species(
            name="Терпуг",
            short_description="x",
            image_url="http://example.com/img.jpg",
            aliases=["терпужок", "terpug"],
        )
    )
    await session.flush()

    resolver = DictionaryResolver(session)

    assert await resolver.resolve_species("терпужок") is not None
    assert await resolver.resolve_species("ТЕРПУЖОК") is not None
    assert await resolver.resolve_species("несуществующая рыба") is None


@pytest.mark.asyncio
async def test_unknown_spot_name_does_not_resolve(session):
    session.add(
        Spot(city_id=1, name="Бухта Новик", lat=43.0, lon=131.9, aliases=["novik"])
    )
    await session.flush()

    resolver = DictionaryResolver(session)

    assert await resolver.resolve_spot("Бухта Новик") is not None
    assert await resolver.resolve_spot("novik") is not None
    assert await resolver.resolve_spot("на Русском") is None, (
        "общее упоминание острова не должно резолвиться в конкретную бухту"
    )
