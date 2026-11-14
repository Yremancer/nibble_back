from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
SortOrder = Annotated[int, Field(ge=0, le=32767)]
Price = Annotated[int, Field(ge=0, le=2_000_000_000)]


def _check_url(value: str) -> str:
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or len(value) > 2000:
        raise ValueError("must be an http(s) link up to 2000 characters")
    return value


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    sort_order: SortOrder = 0


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    sort_order: SortOrder | None = None

    @field_validator("name", "sort_order")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("must not be null")
        return value


class CategoryAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int


class RecommendationIn(BaseModel):

    model_config = ConfigDict(extra="forbid")

    species_id: int | None = None
    method_id: int | None = None
    note: Note | None = None

    @field_validator("note")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _has_target(self) -> "RecommendationIn":
        if self.species_id is None and self.method_id is None:
            raise ValueError("species_id or method_id is required")
        return self


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    species_id: int | None
    method_id: int | None
    note: str | None


def _unique_targets(items: list[RecommendationIn]) -> list[RecommendationIn]:
    pairs = [(r.species_id, r.method_id) for r in items]
    if len(set(pairs)) != len(pairs):
        raise ValueError("recommendations must not repeat")
    return items


class LinkFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    price_from_rub: Price | None = None

    @field_validator("image_url")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


class LinkCreate(LinkFields):
    category_id: int
    city_id: int
    title: Title
    url: str
    sort_order: SortOrder = 0
    is_active: bool = True
    recommendations: list[RecommendationIn] = Field(default_factory=list, max_length=30)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _check_url(value)

    @field_validator("recommendations")
    @classmethod
    def _recommendations(cls, value: list[RecommendationIn]) -> list[RecommendationIn]:
        return _unique_targets(value)


class LinkUpdate(LinkFields):

    category_id: int | None = None
    city_id: int | None = None
    title: Title | None = None
    url: str | None = None
    sort_order: SortOrder | None = None
    is_active: bool | None = None
    recommendations: list[RecommendationIn] | None = Field(None, max_length=30)

    @field_validator("category_id", "city_id", "title", "url", "sort_order", "is_active", "recommendations")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _check_url(value)

    @field_validator("recommendations")
    @classmethod
    def _recommendations(cls, value: list[RecommendationIn]) -> list[RecommendationIn]:
        return _unique_targets(value)


class LinkAdminOut(BaseModel):
    id: int
    category_id: int
    city_id: int
    title: str
    url: str
    image_url: str | None
    price_from_rub: int | None
    price_updated_at: datetime | None
    sort_order: int
    is_active: bool
    recommendations: list[RecommendationOut]
