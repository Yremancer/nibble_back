import httpx
from src.aggregator.exceptions import FarpostUnavailableError
from src.aggregator.sources.farpost_collector import (
    FarpostCollector,
    FarpostHttpError,
    ListingDetail,
)


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
