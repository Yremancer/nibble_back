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

import logging
import re
from dataclasses import dataclass, field

import httpx
from selectolax.parser import HTMLParser

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


class FarpostHttpError(Exception):
    def __init__(self, status_code: int, url: str):
        super().__init__(f"HTTP {status_code} при запросе {url}")
        self.status_code = status_code
        self.url = url


class FarpostCollector:
    def __init__(self, client: httpx.AsyncClient, base_url: str, city_path: str):
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._city_path = city_path.strip("/")

    async def fetch_list_page(self, page: int) -> list[ListingSummary]:
        url = f"{self._base_url}/{self._city_path}/"
        params = {"page": page} if page > 1 else {}
        response = await self._client.get(
            url,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )
        if response.status_code != 200:
            raise FarpostHttpError(response.status_code, url)

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
        return items

    async def fetch_detail(self, url: str, farpost_id: str) -> ListingDetail:
        response = await self._client.get(
            url, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        )
        if response.status_code != 200:
            raise FarpostHttpError(response.status_code, url)

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

        breadcrumb = None
        breadcrumb_nodes = tree.css('script[type="application/ld+json"]')
        for node in breadcrumb_nodes:
            if "BreadcrumbList" in (node.text() or ""):
                import json

                try:
                    data = json.loads(node.text())
                    items = data.get("itemListElement", [])
                    if items:
                        breadcrumb = items[-1].get("name")
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass

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
        )
