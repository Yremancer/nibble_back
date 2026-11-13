"""Привязка скачанных медиафайлов к посту/объявлению с сохранением
единого порядка (attachment_index) и типа (фото/видео)."""

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.listing import ListingMedia
from src.models.media import PostMedia


class PostMediaWriter:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def set_media(
        self, post_id: int, items: list[dict]
    ) -> None:
        """items: [{"media_file_id": int, "type": "photo"|"video", "sort_order": int}]
        Полная замена по посту: повторный импорт пересобирает список из
        уже загруженных вложений (upload идемпотентен по sha256)."""
        await self._session.execute(delete(PostMedia).where(PostMedia.post_id == post_id))
        for item in items:
            self._session.add(
                PostMedia(
                    post_id=post_id,
                    media_file_id=item["media_file_id"],
                    type=item["type"],
                    sort_order=item["sort_order"],
                )
            )
        await self._session.flush()


class ListingMediaWriter:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def set_media(self, listing_id: int, items: list[dict]) -> None:
        await self._session.execute(
            delete(ListingMedia).where(ListingMedia.listing_id == listing_id)
        )
        for item in items:
            self._session.add(
                ListingMedia(
                    listing_id=listing_id,
                    media_file_id=item["media_file_id"],
                    type=item["type"],
                    sort_order=item["sort_order"],
                )
            )
        await self._session.flush()
