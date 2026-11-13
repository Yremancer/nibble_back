import httpx
from src.aggregator.exceptions import DownloadError, FarpostUnavailableError, TelegramUnavailableError
from src.aggregator.schemas import TelegramPostPreview
from src.aggregator.sources.farpost_collector import (
    FarpostCollector,
    FarpostHttpError,
    ListingDetail,
)
from src.aggregator.sources.telegram_public import PublicTelegramCollector


class FarpostService:
    def __init__(self, collector: FarpostCollector):
        self._collector = collector

    async def preview(self, limit: int) -> list[ListingDetail]:
        items = []
        seen = set()
        page = 1
        try:
            while len(items) < limit:
                summaries = await self._collector.fetch_list_page(page)
                new = [summary for summary in summaries if summary.farpost_id not in seen]
                if not new:
                    break
                for summary in new:
                    if summary.farpost_id in seen:
                        continue
                    seen.add(summary.farpost_id)
                    detail = await self._collector.fetch_detail(summary.url, summary.farpost_id)
                    if not detail.title:
                        raise FarpostUnavailableError("Farpost вернул карточку без названия")
                    items.append(detail)
                    if len(items) == limit:
                        break
                page += 1
        except FarpostHttpError as exc:
            detail = f"Farpost вернул HTTP {exc.status_code}" if exc.status_code else "Не удалось подключиться к Farpost"
            raise FarpostUnavailableError(detail) from exc
        except httpx.TimeoutException as exc:
            raise FarpostUnavailableError("Истекло время ожидания ответа Farpost") from exc
        except httpx.HTTPError as exc:
            raise FarpostUnavailableError from exc
        return items


class TelegramService:
    def __init__(self, collector: PublicTelegramCollector):
        self._collector = collector

    async def preview(self, limit: int) -> list[TelegramPostPreview]:
        items = []
        seen = set()
        try:
            async for post in self._collector.iter_preview():
                if post.external_id in seen:
                    continue
                seen.add(post.external_id)
                items.append(post)
                if len(items) == limit:
                    break
        except httpx.TimeoutException as exc:
            raise TelegramUnavailableError("Истекло время ожидания ответа Telegram") from exc
        except httpx.HTTPStatusError as exc:
            raise TelegramUnavailableError(f"Telegram вернул HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, DownloadError, ValueError, KeyError, AttributeError) as exc:
            raise TelegramUnavailableError from exc
        return items
