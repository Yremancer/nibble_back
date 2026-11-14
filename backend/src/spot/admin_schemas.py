from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from src.species.schemas import FishingMethodOut
from src.spot.schemas import SpotShort, SpotSpeciesOut

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Alias = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90, decimal_places=6)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180, decimal_places=6)]


def _unique(values: list, what: str) -> list:
    if len({v.lower() if isinstance(v, str) else v for v in values}) != len(values):
        raise ValueError(f"{what} must not repeat")
    return values


class SpotFields(BaseModel):

    model_config = ConfigDict(extra="forbid")

    area: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None
    photo_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None

    @field_validator("area", "description", "photo_url")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class SpotCreate(SpotFields):
    city_id: int
    name: Name
    lat: Latitude
    lon: Longitude
    aliases: list[Alias] = Field(default_factory=list, max_length=20)
    species_ids: list[int] = Field(default_factory=list, max_length=100)
    method_ids: list[int] = Field(default_factory=list, max_length=50)
    is_active: bool = True

    @field_validator("aliases", "species_ids", "method_ids")
    @classmethod
    def _no_repeats(cls, value: list) -> list:
        return _unique(value, "list items")


class SpotUpdate(SpotFields):

    city_id: int | None = None
    name: Name | None = None
    lat: Latitude | None = None
    lon: Longitude | None = None
    aliases: list[Alias] | None = Field(None, max_length=20)
    species_ids: list[int] | None = Field(None, max_length=100)
    method_ids: list[int] | None = Field(None, max_length=50)
    is_active: bool | None = None

    @field_validator("city_id", "name", "lat", "lon", "aliases", "species_ids", "method_ids", "is_active")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("must not be null")
        return _unique(value, "list items") if isinstance(value, list) else value


class SpotAdminItem(SpotShort):
    is_active: bool
    created_by: int | None


class SpotAdminOut(SpotAdminItem):
    description: str | None
    aliases: list[str]
    species: list[SpotSpeciesOut]
    methods: list[FishingMethodOut]
