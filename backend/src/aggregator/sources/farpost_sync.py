
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import ProcessingStage, RawItemKind
from src.aggregator.repository import (
    CursorRepository,
    MediaAttachmentRepository,
    RawItemRepository,
    TaskRepository,
)
from src.aggregator.sources.farpost_collector import FarpostCollector, FarpostHttpError
from src.city.models import City
from src.models.listing import ListingState
from src.models.tackle import TackleCategory

logger = logging.getLogger(__name__)

PARSER_VERSION = "farpost_v1"
SOURCE_KEY = "farpost"


async def _resolve_category_id(session: AsyncSession, breadcrumb_name: str | None) -> int | None:
    if not breadcrumb_name:
        return None
    result = await session.execute(
        select(TackleCategory).where(TackleCategory.name == breadcrumb_name)
    )
    category = result.scalar_one_or_none()
    return category.id if category else None


async def _resolve_city_id(session: AsyncSession, city_path: str) -> int | None:
    city_name_guess = city_path.strip("/").split("/")[0].replace("-", " ").title()
    result = await session.execute(select(City).where(City.name == city_name_guess))
    city = result.scalar_one_or_none()
    return city.id if city else None


def _classify_state(http_status: int | None) -> ListingState:
    if http_status == 404:
        return ListingState.REMOVED
    return ListingState.UNKNOWN


async def sync_farpost(
    session: AsyncSession,
    collector: FarpostCollector,
    *,
    max_pages: int | None,
    max_listings: int | None,
    city_path: str,
) -> dict:
    cursor_repo = CursorRepository(session)
    raw_items_repo = RawItemRepository(session)
    attachments_repo = MediaAttachmentRepository(session)
    tasks_repo = TaskRepository(session)

    cursor = await cursor_repo.get(SOURCE_KEY, "incremental")
    start_page = cursor.get("next_page", 1) if cursor else 1

    stats = {"fetched": 0, "created": 0, "updated": 0, "errors": 0}
    processed = 0
    page = start_page
    city_id = await _resolve_city_id(session, city_path)

    try:
        while True:
            if max_pages is not None and page - start_page >= max_pages:
                break

            summaries = await collector.fetch_list_page(page)
            if not summaries:
                break

            for summary in summaries:
                if max_listings is not None and processed >= max_listings:
                    break
                processed += 1
                stats["fetched"] += 1

                try:
                    detail = await collector.fetch_detail(summary.url, summary.farpost_id)
                except FarpostHttpError as exc:
                    logger.warning("farpost detail failed %s: %s", summary.url, exc)
                    stats["errors"] += 1
                    continue

                category_id = await _resolve_category_id(session, detail.category_breadcrumb)

                raw_payload = {
                    "farpost_id": detail.farpost_id,
                    "title": detail.title,
                    "url": detail.url,
                    "description": detail.description,
                    "price_rub": detail.price_rub,
                    "price_raw": detail.price_raw,
                    "photo_urls": detail.photo_urls,
                    "seller_name": detail.seller_name,
                    "seller_url": detail.seller_url,
                    "characteristics": detail.characteristics,
                    "category_id": category_id,
                    "city_id": city_id,
                    "state": ListingState.ACTIVE.value,
                }

                import hashlib
                import json

                content_hash_value = hashlib.sha256(
                    json.dumps(raw_payload, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()

                item, changed, is_new = await raw_items_repo.upsert_raw_item(
                    kind=RawItemKind.FARPOST_LISTING.value,
                    source_key=SOURCE_KEY,
                    external_id=detail.farpost_id,
                    raw_payload=raw_payload,
                    content_hash=content_hash_value,
                    parser_version=PARSER_VERSION,
                )

                for index, photo_url in enumerate(detail.photo_urls):
                    await attachments_repo.upsert(item.id, index, photo_url, "photo")

                if changed:
                    await tasks_repo.enqueue(item.id, ProcessingStage.MEDIA)

                stats["created" if is_new else "updated"] += 1

            if max_listings is not None and processed >= max_listings:
                break

            page += 1
            await asyncio.sleep(0)

    except FarpostHttpError as exc:
        logger.error("farpost обход остановлен: %s", exc)
        stats["errors"] += 1
        stats["stopped_reason"] = str(exc)

    await cursor_repo.set(SOURCE_KEY, "incremental", {"next_page": page})

    return stats
