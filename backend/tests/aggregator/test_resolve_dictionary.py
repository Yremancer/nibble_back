
import pytest
from src.aggregator.resolve.dictionary import DictionaryResolver
from src.city.models import City
from src.spot.models import Spot
from src.species.models import Species


@pytest.mark.asyncio
async def test_species_resolved_by_alias(session):
    session.add(
        Species(
            name="Тестовый терпуг",
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
    city = City(name="Тестовый город", lat=43.0, lon=131.9, timezone="Asia/Vladivostok")
    session.add(city)
    await session.flush()
    session.add(
        Spot(city_id=city.id, name="Бухта Новик", lat=43.0, lon=131.9, aliases=["novik"])
    )
    await session.flush()

    resolver = DictionaryResolver(session)

    assert await resolver.resolve_spot("Бухта Новик") is not None
    assert await resolver.resolve_spot("novik") is not None
    assert await resolver.resolve_spot("на Русском") is None, (
        "общее упоминание острова не должно резолвиться в конкретную бухту"
    )
