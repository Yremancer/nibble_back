
import hashlib
import json
import logging
from itertools import chain, count
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.config import aggregator_settings
from src.aggregator.models import ProcessingStage, RawItemKind
from src.aggregator.repository import CursorRepository, MediaAttachmentRepository, RawItemRepository, TaskRepository
from src.aggregator.sources.farpost_collector import FarpostCollector, FarpostHttpError
from src.city.models import City
from src.models.listing import ListingState
from src.models.tackle import TackleCategory

logger = logging.getLogger(__name__)
PARSER_VERSION = "farpost_v2"
SOURCE_KEY = "farpost"
_CITY_SLUGS = {
    "vladivostok": "Владивосток", "nakhodka": "Находка",
    "ussuriisk": "Уссурийск", "ussurijsk": "Уссурийск", "artem": "Артём",
}


async def _resolve_category_id(session: AsyncSession, breadcrumb_name: str | None) -> int | None:
    if not breadcrumb_name:
        return None
    return await session.scalar(select(TackleCategory.id).where(TackleCategory.name == breadcrumb_name))


async def _resolve_city_id(session: AsyncSession, city_path: str, city_name: str | None = None) -> int | None:
    name = city_name or _CITY_SLUGS.get(city_path.strip("/").split("/")[0])
    if not name:
        return None
    return await session.scalar(select(City.id).where(
        func.lower(func.replace(City.name, "ё", "е")) == name.lower().replace("ё", "е"),
    ))


def _classify_state(http_status: int | None) -> ListingState:
    return ListingState.REMOVED if http_status == 404 else ListingState.UNKNOWN


async def ingest_farpost_listing(session: AsyncSession, payload: dict) -> tuple[bool, bool]:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    item, changed, is_new = await RawItemRepository(session).upsert_raw_item(
        kind=RawItemKind.FARPOST_LISTING.value, source_key=SOURCE_KEY,
        external_id=payload["farpost_id"], raw_payload=payload,
        content_hash=digest, parser_version=PARSER_VERSION,
    )
    photos = payload.get("photo_urls") or []
    attachments = MediaAttachmentRepository(session)
    for index, url in enumerate(photos):
        await attachments.upsert(item.id, index, url, "photo")
    await attachments.delete_after(item.id, len(photos))
    if changed:
        await TaskRepository(session).enqueue(item.id, ProcessingStage.MEDIA if photos else ProcessingStage.PUBLISH)
    return is_new, changed


async def sync_farpost(
    session: AsyncSession, collector: FarpostCollector, *,
    max_pages: int | None, max_listings: int | None, city_path: str,
) -> dict:
    cursor_repo = CursorRepository(session)
    cursor = await cursor_repo.get(SOURCE_KEY, "incremental")
    next_page = max(1, cursor.get("next_page", 1)) if cursor else 1
    fresh_pages = aggregator_settings.FARPOST_RECHECK_PAGES
    pages = chain(range(1, fresh_pages + 1), count(max(next_page, fresh_pages + 1)))
    stats = {"fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "errors": 0, "pages": 0}
    visited = set()
    seen_ids = set()
    try:
        for page in pages:
            if max_pages is not None and stats["pages"] >= max_pages:
                break
            if max_listings is not None and stats["fetched"] >= max_listings:
                break
            stats["pages"] += 1
            summaries = await collector.fetch_list_page(page)
            if not summaries:
                next_page = 1
                break
            page_failed = False
            page_complete = True
            for summary in summaries:
                if summary.farpost_id in seen_ids:
                    continue
                if max_listings is not None and stats["fetched"] >= max_listings:
                    page_complete = False
                    break
                seen_ids.add(summary.farpost_id)
                stats["fetched"] += 1
                try:
                    detail = await collector.fetch_detail(summary.url, summary.farpost_id)
                    async with session.begin_nested():
                        payload = {
                            "farpost_id": detail.farpost_id, "title": detail.title, "url": detail.url,
                            "description": detail.description, "price_rub": detail.price_rub,
                            "price_raw": detail.price_raw, "photo_urls": detail.photo_urls,
                            "seller_name": detail.seller_name, "seller_url": detail.seller_url,
                            "characteristics": detail.characteristics,
                            "category_id": await _resolve_category_id(session, detail.category_breadcrumb),
                            "city_id": await _resolve_city_id(session, urlsplit(detail.url).path, detail.city_name),
                            "state": ListingState.ACTIVE.value,
                        }
                        is_new, changed = await ingest_farpost_listing(session, payload)
                    stats["created" if is_new else "updated" if changed else "unchanged"] += 1
                except FarpostHttpError as exc:
                    if exc.stops_run:
                        raise
                    logger.warning("farpost detail failed: %s", exc)
                    stats["errors"] += 1
                    page_failed = True
                except Exception:
                    logger.exception("farpost record failed: %s", summary.farpost_id)
                    stats["errors"] += 1
                    page_failed = True
            if page_complete and not page_failed:
                visited.add(page)
                while next_page in visited:
                    next_page += 1
            elif page >= next_page:
                next_page = page
                break
    except FarpostHttpError as exc:
        logger.error("farpost обход остановлен: %s", exc)
        stats["errors"] += 1
        stats["stopped_reason"] = str(exc)
        if exc.status_code in (403, 429, 503):
            stats["manual_import"] = "import-listings --input /app/data/listings.json"
    await cursor_repo.set(SOURCE_KEY, "incremental", {"next_page": next_page})
    return stats
