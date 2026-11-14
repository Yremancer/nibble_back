from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from src.species.schemas import SpeciesOut

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Alias = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Month = Annotated[int, Field(ge=1, le=12)]


def _unique(values: list, what: str) -> list:
    if len({v.lower() if isinstance(v, str) else v for v in values}) != len(values):
        raise ValueError(f"{what} must not repeat")
    return values


class SpeciesFields(BaseModel):

    model_config = ConfigDict(extra="forbid")

    latin_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None = None
    identification: Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)] | None = None
    typical_length_cm: Annotated[int, Field(gt=0, le=32767)] | None = None
    typical_weight_g: Annotated[int, Field(gt=0, le=2_000_000_000)] | None = None

    @field_validator("latin_name", "description", "identification")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class SpeciesCreate(SpeciesFields):
    name: Name
    short_description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    image_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    months: list[Month] = Field(min_length=1, max_length=12)
    aliases: list[Alias] = Field(default_factory=list, max_length=30)

    @field_validator("months", "aliases")
    @classmethod
    def _no_repeats(cls, value: list) -> list:
        return _unique(value, "list items")


class SpeciesUpdate(SpeciesFields):

    name: Name | None = None
    short_description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    image_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None
    months: list[Month] | None = Field(None, min_length=1, max_length=12)
    aliases: list[Alias] | None = Field(None, max_length=30)

    @field_validator("name", "short_description", "image_url", "months", "aliases")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("must not be null")
        return _unique(value, "list items") if isinstance(value, list) else value


class SpeciesAdminOut(SpeciesOut):
    aliases: list[str]

    @field_validator("aliases", mode="before")
    @classmethod
    def _aliases(cls, value: list[str] | None) -> list[str]:
        return value or []


class MethodCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name


class MethodUpdate(MethodCreate):
    pass
