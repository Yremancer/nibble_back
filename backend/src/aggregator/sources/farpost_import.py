import asyncio
import csv
import io
import json
from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.aggregator.sources.farpost_sync import _resolve_category_id, _resolve_city_id, ingest_farpost_listing
from src.models.listing import ListingState


class ManualListing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farpost_id: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=255)
    url: AnyHttpUrl
    city: str | None = None
    category: str | None = None
    description: str | None = None
    price_rub: int | None = Field(default=None, ge=0)
    price_raw: str | None = Field(default=None, max_length=100)
    photo_urls: list[AnyHttpUrl] = Field(default_factory=list)
    seller_name: str | None = Field(default=None, max_length=255)
    seller_url: AnyHttpUrl | None = None
    characteristics: dict[str, str] = Field(default_factory=dict)
    state: ListingState = ListingState.ACTIVE

    @field_validator("url")
    @classmethod
    def farpost_url(cls, value):
        if value.host not in ("farpost.ru", "www.farpost.ru") or value.username or value.password:
            raise ValueError("url должен вести на farpost.ru без credentials")
        return value


def _read_rows(path: Path) -> list:
    content = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        rows = json.loads(content)
        if not isinstance(rows, list):
            raise ValueError("JSON должен содержать массив объявлений")
        return rows
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(io.StringIO(content)))
    raise ValueError("поддерживаются .csv и .json")


def parse_manual_listing(row: dict) -> ManualListing:
    if not isinstance(row, dict):
        raise ValueError("объявление должно быть объектом")
    row = {key: value for key, value in row.items() if value != ""}
    if isinstance(row.get("photo_urls"), str):
        value = row["photo_urls"].strip()
        row["photo_urls"] = json.loads(value) if value.startswith("[") else [url.strip() for url in value.split(";") if url.strip()]
    if isinstance(row.get("characteristics"), str):
        row["characteristics"] = json.loads(row["characteristics"])
    return ManualListing.model_validate(row)


async def import_listings(session: AsyncSession, path: Path, *, city: str | None = None) -> dict:
    rows = await asyncio.to_thread(_read_rows, path)
    stats = {"fetched": len(rows), "created": 0, "updated": 0, "unchanged": 0, "errors": 0, "row_errors": []}
    for index, row in enumerate(rows, 1):
        try:
            item = parse_manual_listing(row)
            async with session.begin_nested():
                city_name = item.city or city
                city_id = await _resolve_city_id(session, item.url.path or "", city_name)
                if city_name and city_id is None:
                    raise ValueError("город отсутствует в справочнике")
                payload = item.model_dump(mode="json", exclude={"city", "category"})
                payload["city_id"] = city_id
                payload["category_id"] = await _resolve_category_id(session, item.category)
                is_new, changed = await ingest_farpost_listing(session, payload)
            stats["created" if is_new else "updated" if changed else "unchanged"] += 1
        except Exception as exc:
            stats["errors"] += 1
            stats["row_errors"].append({"row": index, "error": str(exc)[:2000]})
    return stats
