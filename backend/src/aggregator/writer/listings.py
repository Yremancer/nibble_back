
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.listing import Listing, ListingPriceHistory, ListingState


class ListingWriter:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_farpost_id(self, farpost_id: str) -> Listing | None:
        result = await self._session.execute(
            select(Listing).where(Listing.farpost_id == farpost_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        farpost_id: str,
        category_id: int | None,
        city_id: int | None,
        title: str,
        description: str | None,
        price_rub: int | None,
        price_raw: str | None,
        photo_url: str | None,
        url: str,
        seller_name: str | None,
        seller_url: str | None,
        characteristics: dict | None,
        state: ListingState,
    ) -> tuple[Listing, bool]:
        existing = await self.get_by_farpost_id(farpost_id)
        now = datetime.now(timezone.utc)

        price_changed = False
        if existing is None:
            listing = Listing(
                farpost_id=farpost_id,
                category_id=category_id,
                city_id=city_id,
                title=title,
                description=description,
                price_rub=price_rub,
                price_raw=price_raw,
                photo_url=photo_url,
                url=url,
                is_active=(state == ListingState.ACTIVE),
                state=state.value,
                seller_name=seller_name,
                seller_url=seller_url,
                characteristics=characteristics,
                last_seen_at=now,
            )
            self._session.add(listing)
            await self._session.flush()
            price_changed = True
        else:
            listing = existing
            price_changed = (
                listing.price_rub != price_rub or listing.price_raw != price_raw
            )
            listing.title = title
            listing.description = description
            listing.price_rub = price_rub
            listing.price_raw = price_raw
            listing.photo_url = photo_url
            listing.url = url
            listing.seller_name = seller_name
            listing.seller_url = seller_url
            listing.characteristics = characteristics
            listing.last_seen_at = now
            if category_id is not None:
                listing.category_id = category_id
            if city_id is not None:
                listing.city_id = city_id
            self._apply_state(listing, state)
            await self._session.flush()

        if price_changed or existing is None:
            self._session.add(
                ListingPriceHistory(
                    listing_id=listing.id,
                    price_rub=price_rub,
                    price_raw=price_raw,
                    state=state.value,
                )
            )
            await self._session.flush()

        return listing, existing is None

    def _apply_state(self, listing: Listing, new_state: ListingState) -> None:
        if new_state == ListingState.UNKNOWN:
            return
        listing.state = new_state.value
        listing.is_active = new_state == ListingState.ACTIVE

    async def mark_not_seen(self, listing: Listing) -> None:
        if listing.state == ListingState.ACTIVE.value:
            listing.state = ListingState.UNKNOWN.value
            await self._session.flush()
