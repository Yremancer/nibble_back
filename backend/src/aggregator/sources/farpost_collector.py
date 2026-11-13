"""Farpost сборщик: HTTP + HTML-парсер (selectolax), без браузера.

Структура страниц подтверждена живым запросом (см. отчёт):
- список: GET {base}/{city}/sport/fish/?page=N, windows-1251,
  карточки `tr[data-doc-id]` -> `div[data-bulletin-id]`.
- детальная карточка: GET {base}/{city}/sport/fish/<slug>-<id>.html,
  текст описания в `[data-field="text"]`, цена в `[data-field="price"]`,
  галерея в `img.image-gallery__big-image`, продавец в `.seller-summary`.

Фарпост отдаёт windows-1251 и выставляет anti-bot cookies (ring/ring_session) —
сессия httpx с cookie jar обязательна. 403/сетевые ошибки не считаются
подтверждением снятия объявления (см. ТЗ, раздел 12).
"""

import asyncio
import logging
import re
from time import monotonic
from urllib.parse import urljoin, urlsplit
from dataclasses import dataclass, field

import httpx
from selectolax.parser import HTMLParser
from src.aggregator.config import aggregator_settings

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

_PRICE_DIGITS_RE = re.compile(r"[\d\s]+")


@dataclass
class ListingSummary:
    farpost_id: str
    title: str
    url: str


@dataclass
class ListingDetail:
    farpost_id: str
    title: str
    url: str
    description: str | None
    price_rub: int | None
    price_raw: str | None
    photo_urls: list[str]
    seller_name: str | None
    seller_url: str | None
    characteristics: dict = field(default_factory=dict)
    category_breadcrumb: str | None = None
    city_name: str | None = None


class FarpostHttpError(Exception):
    def __init__(self, status_code: int, url: str, reason: str | None = None):
        super().__init__(f"HTTP {status_code} при запросе {url}" + (f": {reason}" if reason else ""))
        self.status_code = status_code
        self.url = url

    @property
    def stops_run(self) -> bool:
        return self.status_code in (0, 401, 403, 429, 503)


class FarpostCollector:
    def __init__(self, client: httpx.AsyncClient, base_url: str, city_path: str, *, delay: float | None = None):
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._city_path = city_path.strip("/")
        self._delay = aggregator_settings.FARPOST_REQUEST_DELAY_S if delay is None else delay
        self._next_request_at = 0.0
        self._request_lock = asyncio.Lock()

    async def _get(self, url: str, *, params: dict | None = None) -> httpx.Response:
        async with self._request_lock:
            for _ in range(6):
                parsed = urlsplit(url)
                if parsed.scheme not in ("http", "https") or parsed.hostname != urlsplit(self._base_url).hostname or parsed.username:
                    raise FarpostHttpError(403, url, "ссылка за пределами источника")
                await asyncio.sleep(max(0, self._next_request_at - monotonic()))
                try:
                    response = await self._client.get(
                        url, params=params, headers={"User-Agent": _USER_AGENT}, follow_redirects=False,
                    )
                except httpx.HTTPError as exc:
                    raise FarpostHttpError(0, url, type(exc).__name__) from exc
                finally:
                    self._next_request_at = monotonic() + self._delay
                if response.is_redirect:
                    target = urljoin(url, response.headers.get("location", ""))
                    if urlsplit(target).hostname != urlsplit(self._base_url).hostname:
                        raise FarpostHttpError(403, url, "редирект за пределы источника")
                    url, params = target, None
                    continue
                if response.status_code != 200:
                    raise FarpostHttpError(response.status_code, url)
                tree = HTMLParser(response.content.decode("windows-1251", errors="replace"))
                title = tree.css_first("title")
                if tree.css_first('form[action*="captcha"], input[name*="captcha"], #captcha') or (
                    title and any(word in title.text().lower() for word in ("captcha", "доступ ограничен", "проверка браузера", "access denied"))
                ):
                    raise FarpostHttpError(403, url, "источник запросил проверку доступа")
                return response
        raise FarpostHttpError(403, url, "слишком много перенаправлений")

    async def fetch_list_page(self, page: int) -> list[ListingSummary]:
        url = f"{self._base_url}/{self._city_path}/"
        params = {"page": page} if page > 1 else {}
        response = await self._get(url, params=params)

        html = response.content.decode("windows-1251", errors="replace")
        tree = HTMLParser(html)

        items: list[ListingSummary] = []
        for node in tree.css("div[data-bulletin-id]"):
            farpost_id = node.attributes.get("data-bulletin-id")
            link_node = node.css_first("a.bulletinLink")
            if not farpost_id or not link_node:
                continue
            href = link_node.attributes.get("href", "")
            full_url = href if href.startswith("http") else f"{self._base_url}{href}"
            items.append(
                ListingSummary(
                    farpost_id=farpost_id,
                    title=link_node.text(strip=True),
                    url=full_url,
                )
            )
        if not items and not any(marker in html.lower() for marker in ("ничего не найдено", "объявлений не найдено", "нет объявлений")):
            raise FarpostHttpError(200, url, "не найдены карточки; проверьте разметку или используйте import-listings")
        return items

    async def fetch_detail(self, url: str, farpost_id: str) -> ListingDetail:
        response = await self._get(url)

        html = response.content.decode("windows-1251", errors="replace")
        tree = HTMLParser(html)

        title_node = tree.css_first('h1 span[data-field="subject"]')
        title = ""
        if title_node:
            nobr_node = title_node.css_first("nobr")
            if nobr_node:
                nobr_node.decompose()
            title = title_node.text(strip=True)

        text_node = tree.css_first('[data-field="text"]')
        description = text_node.text(deep=True, separator="\n").strip() if text_node else None

        price_node = tree.css_first('[data-field="price"]')
        price_raw = None
        price_rub = None
        if price_node:
            price_text = price_node.text(strip=True)
            price_raw = price_text
            digits = re.sub(r"\D", "", price_text)
            if digits:
                price_rub = int(digits)

        photo_urls = []
        seen = set()
        for img in tree.css("img.image-gallery__big-image"):
            src = img.attributes.get("src")
            if src and src not in seen:
                seen.add(src)
                photo_urls.append(src.replace("_bulletin", "_default"))

        seller_node = tree.css_first(".seller-summary-user .userNick a")
        seller_name = seller_node.text(strip=True) if seller_node else None
        seller_url = None
        if seller_node:
            href = seller_node.attributes.get("href")
            if href:
                seller_url = href if href.startswith("http") else f"{self._base_url}{href}"

        characteristics: dict[str, str] = {}
        for field_node in tree.css(".field.viewbull-field__container"):
            label_node = field_node.css_first(".label")
            value_node = field_node.css_first(".value")
            if label_node and value_node:
                key = label_node.text(strip=True)
                value = value_node.text(strip=True)
                if key and value:
                    characteristics[key] = value

        if not title:
            raise FarpostHttpError(200, url, "не найден заголовок объявления")
        breadcrumb = None
        city_name = None
        breadcrumb_nodes = tree.css('script[type="application/ld+json"]')
        for node in breadcrumb_nodes:
            import json

            try:
                data = json.loads(node.text())
            except (json.JSONDecodeError, TypeError):
                continue
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                items = entry.get("itemListElement", [])
                if entry.get("@type") == "BreadcrumbList" and items:
                    breadcrumb = items[-1].get("name")
                location = entry.get("location")
                address = entry.get("address") or (location.get("address") if isinstance(location, dict) else None)
                if isinstance(address, dict):
                    city_name = address.get("addressLocality") or city_name

        return ListingDetail(
            farpost_id=farpost_id,
            title=title,
            url=url,
            description=description,
            price_rub=price_rub,
            price_raw=price_raw,
            photo_urls=photo_urls,
            seller_name=seller_name,
            seller_url=seller_url,
            characteristics=characteristics,
            category_breadcrumb=breadcrumb,
            city_name=city_name,
        )
