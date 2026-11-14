from src.settings import settings
from src.tackle.repository import TackleRepository, applies
from src.tackle.schemas import CategoryOut, TackleLinkOut, TackleQuery


def with_utm(url: str, params: str) -> str:
    """Добавляет метку к исходящей ссылке, не трогая остальные параметры."""
    if not params or "utm_source=" in url:
        return url
    base, hash_sep, fragment = url.partition("#")
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}{params}{hash_sep}{fragment}"


class TackleService:
    def __init__(self, repo: TackleRepository) -> None:
        self.repo = repo

    async def list_categories(self) -> list[CategoryOut]:
        return [CategoryOut.model_validate(c) for c in await self.repo.list_categories()]

    async def list_links(self, query: TackleQuery) -> list[TackleLinkOut]:
        rows = await self.repo.list_links(
            city_id=query.city_id,
            category_id=query.category_id,
            species_id=query.species_id,
            method_id=query.method_id,
            limit=query.limit,
        )
        recs = await self.repo.recommendations_by_link([link.id for link, _ in rows])
        items = []
        for link, category in rows:
            notes = []
            for rec in recs[link.id]:
                if rec.note and applies(rec, query.species_id, query.method_id) and rec.note not in notes:
                    notes.append(rec.note)
            items.append(
                TackleLinkOut(
                    id=link.id,
                    category=CategoryOut.model_validate(category),
                    title=link.title,
                    url=with_utm(link.url, settings.TACKLE_UTM_PARAMS),
                    image_url=link.image_url,
                    price_from_rub=link.price_from_rub,
                    price_updated_at=link.price_updated_at,
                    notes=notes,
                )
            )
        return items
