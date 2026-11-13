
import logging
import re
from dataclasses import dataclass, field

import httpx
from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

_MONTHS_RU = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

_YANDEX_SHORTLINK_RE = re.compile(r"https://yandex\.ru/map-widget/v1/[^\"\s]+")
_LL_PARAM_RE = re.compile(r"[?&]ll=([\-\d.]+)%2C([\-\d.]+)")


@dataclass
class SpotCandidate:
    slug: str
    name: str
    url: str
    description: str | None = None
    photo_urls: list[str] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    fish_by_month: dict[str, list[str]] = field(default_factory=dict)


class FishingVlCollector:
    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def list_place_slugs(self) -> list[str]:
        slugs: set[str] = set()
        for month in _MONTHS_RU:
            response = await self._client.get(f"{self._base_url}/places/{month}/")
            if response.status_code != 200:
                continue
            tree = HTMLParser(response.text)
            for link in tree.css('a[href^="/place/"]'):
                href = link.attributes.get("href", "")
                slug_match = re.match(r"^/place/([^/]+)/?$", href)
                if slug_match:
                    slugs.add(slug_match.group(1))
        return sorted(slugs)

    async def fetch_place(self, slug: str) -> SpotCandidate:
        url = f"{self._base_url}/place/{slug}/"
        response = await self._client.get(url)
        response.raise_for_status()
        tree = HTMLParser(response.text)

        title_node = tree.css_first("h1")
        name = title_node.text(strip=True) if title_node else slug

        desc_node = tree.css_first(".content__description")
        description = desc_node.text(deep=True, separator="\n").strip() if desc_node else None

        photo_urls = [
            img.attributes.get("src")
            for img in tree.css(".content__description img")
            if img.attributes.get("src")
        ]

        lat = lon = None
        shortlink_match = _YANDEX_SHORTLINK_RE.search(response.text)
        if shortlink_match:
            lat, lon = await self._resolve_yandex_shortlink(shortlink_match.group(0))

        fish_by_month = _extract_fish_in_place(response.text)

        return SpotCandidate(
            slug=slug,
            name=name,
            url=url,
            description=description,
            photo_urls=photo_urls,
            lat=lat,
            lon=lon,
            fish_by_month=fish_by_month,
        )

    async def _resolve_yandex_shortlink(self, shortlink: str) -> tuple[float | None, float | None]:
        try:
            response = await self._client.get(shortlink, follow_redirects=False)
        except httpx.HTTPError as exc:
            logger.warning("не удалось резолвить shortlink %s: %s", shortlink, exc)
            return None, None

        location = response.headers.get("location")
        if not location:
            return None, None

        match = _LL_PARAM_RE.search(location)
        if not match:
            return None, None
        lon, lat = float(match.group(1)), float(match.group(2))
        return lat, lon


def _extract_fish_in_place(html: str) -> dict[str, list[str]]:
    match = re.search(r"window\.fishInPlaceData\s*=\s*(\[[\s\S]*?\]);", html)
    if not match:
        return {}
    try:
        import ast

        raw = match.group(1)
        raw = re.sub(r",\s*\]", "]", raw)
        data = ast.literal_eval(raw)
    except (ValueError, SyntaxError, TypeError):
        return {}

    if not data or len(data) < 2:
        return {}
    header = data[0]
    species_names = header[1:]
    result: dict[str, list[str]] = {}
    for row in data[1:]:
        month = row[0]
        present = [
            species_names[i - 1]
            for i in range(1, len(row))
            if isinstance(row[i], (int, float)) and row[i] > 0
        ]
        if present:
            result[month] = present
    return result
