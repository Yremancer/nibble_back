"""Публикация объявлений Фарпоста в доменную модель listings. В отличие от
постов, здесь нет классификации рекламы (Фарпост не фильтруется) и нет
дедупликации по тексту — только farpost_id как стабильный ключ (см. ТЗ,
раздел 9 и 11)."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import AggRawItem
from src.aggregator.repository import MediaAttachmentRepository, RawItemRepository
from src.aggregator.writer.listings import ListingWriter
from src.aggregator.writer.media import ListingMediaWriter
from src.models.listing import ListingState

logger = logging.getLogger(__name__)


async def publish_pending_listings(session: AsyncSession, raw_item_ids: list[int]) -> dict:
    raw_items_repo = RawItemRepository(session)
    attachments_repo = MediaAttachmentRepository(session)
    listing_writer = ListingWriter(session)
    media_writer = ListingMediaWriter(session)

    done = failed = 0

    for raw_item_id in raw_item_ids:
        try:
            async with session.begin_nested():
                raw_item: AggRawItem | None = await session.get(AggRawItem, raw_item_id)
                if raw_item is None or raw_item.kind != "farpost_listing":
                    continue

                payload = raw_item.raw_payload
                listing, _ = await listing_writer.upsert(
                    farpost_id=payload["farpost_id"],
                    category_id=payload.get("category_id"),
                    city_id=payload.get("city_id"),
                    title=payload["title"],
                    description=payload.get("description"),
                    price_rub=payload.get("price_rub"),
                    price_raw=payload.get("price_raw"),
                    photo_url=(payload.get("photo_urls") or [None])[0],
                    url=payload["url"],
                    seller_name=payload.get("seller_name"),
                    seller_url=payload.get("seller_url"),
                    characteristics=payload.get("characteristics"),
                    state=ListingState(payload.get("state", "unknown")),
                )

                if raw_item.listing_id is None:
                    await raw_items_repo.link_listing(raw_item.id, listing.id)

                attachments = await attachments_repo.all_for_item(raw_item_id)
                media_items = [
                    {
                        "media_file_id": a.media_file_id,
                        "type": a.media_type,
                        "sort_order": a.attachment_index,
                    }
                    for a in attachments
                    if a.media_file_id is not None
                ]
                if media_items:
                    await media_writer.set_media(listing.id, media_items)

                done += 1
        except Exception:
            logger.exception("publish listing failed for raw_item %s", raw_item_id)
            failed += 1

    return {"done": done, "failed": failed}
