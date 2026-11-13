
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.spot.models import Spot
from src.species.models import FishingMethod, Species


def _normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).lower().strip()
    name = re.sub(r"[^\w\s]", "", name, flags=re.UNICODE)
    return re.sub(r"\s+", " ", name)


class DictionaryResolver:

    def __init__(self, session: AsyncSession):
        self._session = session
        self._species_index: dict[str, int] | None = None
        self._spot_index: dict[str, int] | None = None
        self._method_index: dict[str, int] | None = None

    async def _load_species_index(self) -> dict[str, int]:
        if self._species_index is None:
            result = await self._session.execute(select(Species))
            index: dict[str, int] = {}
            for species in result.scalars():
                index[_normalize_name(species.name)] = species.id
                for alias in species.aliases or []:
                    index[_normalize_name(alias)] = species.id
            self._species_index = index
        return self._species_index

    async def _load_spot_index(self) -> dict[str, int]:
        if self._spot_index is None:
            result = await self._session.execute(select(Spot))
            index: dict[str, int] = {}
            for spot in result.scalars():
                index[_normalize_name(spot.name)] = spot.id
                for alias in spot.aliases or []:
                    index[_normalize_name(alias)] = spot.id
            self._spot_index = index
        return self._spot_index

    async def _load_method_index(self) -> dict[str, int]:
        if self._method_index is None:
            result = await self._session.execute(select(FishingMethod))
            self._method_index = {
                _normalize_name(m.name): m.id for m in result.scalars()
            }
        return self._method_index

    async def resolve_species(self, raw_name: str) -> int | None:
        index = await self._load_species_index()
        return index.get(_normalize_name(raw_name))

    async def resolve_spot(self, raw_name: str) -> int | None:
        index = await self._load_spot_index()
        return index.get(_normalize_name(raw_name))

    async def resolve_method(self, raw_name: str) -> int | None:
        index = await self._load_method_index()
        return index.get(_normalize_name(raw_name))
