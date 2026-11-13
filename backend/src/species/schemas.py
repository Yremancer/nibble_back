from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class Season(StrEnum):
    WINTER = "winter"
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"


SEASON_MONTHS = {
    Season.WINTER: (12, 1, 2),
    Season.SPRING: (3, 4, 5),
    Season.SUMMER: (6, 7, 8),
    Season.AUTUMN: (9, 10, 11),
}


class SpeciesShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_description: str
    image_url: str
    months: list[int]

    @field_validator("months", mode="before")
    @classmethod
    def _months(cls, value: list) -> list[int]:
        return [m if isinstance(m, int) else m.month for m in value]


class SpeciesOut(SpeciesShort):
    latin_name: str | None
    description: str | None
    identification: str | None
    typical_length_cm: int | None
    typical_weight_g: int | None


class FishingMethodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
