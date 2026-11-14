from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from src.spot.schemas import SpotShort


class SearchQuery(BaseModel):
    q: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    city_id: int | None = None
    limit: int = Field(10, ge=1, le=20)


class SpeciesHit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    latin_name: str | None
    short_description: str
    image_url: str


class SearchResult(BaseModel):
    spots: list[SpotShort]
    species: list[SpeciesHit]
