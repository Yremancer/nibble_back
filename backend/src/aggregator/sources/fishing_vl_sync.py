
import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import CandidateKind, RawItemKind
from src.aggregator.repository import CandidateRepository, RawItemRepository
from src.aggregator.sources.fishing_vl_collector import FishingVlCollector
from src.city.models import City
from src.spot.models import Spot

logger = logging.getLogger(__name__)

PARSER_VERSION = "fishing_vl_v1"
SOURCE_KEY = "fishing_vl"


async def _default_city_id(session: AsyncSession) -> int | None:
    result = await session.execute(select(City).order_by(City.id).limit(1))
    city = result.scalar_one_or_none()
    return city.id if city else None


async def sync_fishing_vl_spots(
    session: AsyncSession,
    collector: FishingVlCollector,
    *,
    limit: int | None = None,
) -> dict:
    raw_items_repo = RawItemRepository(session)
    candidates_repo = CandidateRepository(session)

    slugs = await collector.list_place_slugs()
    if limit is not None:
        slugs = slugs[:limit]

    city_id = await _default_city_id(session)
    stats = {"fetched": 0, "created_spots": 0, "candidates": 0, "errors": 0}

    for slug in slugs:
        stats["fetched"] += 1
        try:
            place = await collector.fetch_place(slug)
        except Exception:
            logger.exception("fishing_vl fetch_place failed for %s", slug)
            stats["errors"] += 1
            continue

        raw_payload = {
            "slug": place.slug,
            "name": place.name,
            "url": place.url,
            "description": place.description,
            "photo_urls": place.photo_urls,
            "lat": place.lat,
            "lon": place.lon,
            "fish_by_month": place.fish_by_month,
        }
        content_hash_value = hashlib.sha256(
            json.dumps(raw_payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        item, changed, is_new = await raw_items_repo.upsert_raw_item(
            kind=RawItemKind.FISHING_VL_SPOT.value,
            source_key=SOURCE_KEY,
            external_id=place.slug,
            raw_payload=raw_payload,
            content_hash=content_hash_value,
            parser_version=PARSER_VERSION,
        )

        if not changed:
            continue

        if place.lat is not None and place.lon is not None and city_id is not None:
            result = await session.execute(select(Spot).where(Spot.name == place.name))
            existing_spot = result.scalar_one_or_none()
            if existing_spot is None:
                spot = Spot(
                    city_id=city_id,
                    name=place.name,
                    description=place.description,
                    lat=place.lat,
                    lon=place.lon,
                    photo_url=place.photo_urls[0] if place.photo_urls else None,
                    aliases=[place.slug],
                )
                session.add(spot)
                await session.flush()
                await raw_items_repo.link_spot(item.id, spot.id)
                stats["created_spots"] += 1
        else:
            await candidates_repo.add(
                item.id,
                CandidateKind.SPOT.value,
                place.name,
                "координаты не удалось определить (fishing-vl.ru)",
            )
            stats["candidates"] += 1

    return stats
