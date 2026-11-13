from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from src.species.schemas import FishingMethodOut


class SpotShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city_id: int
    name: str
    area: str | None
    lat: Decimal
    lon: Decimal
    photo_url: str | None


class SpotSpeciesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image_url: str


class SpotOut(SpotShort):
    description: str | None
    species: list[SpotSpeciesOut]
    methods: list[FishingMethodOut]
