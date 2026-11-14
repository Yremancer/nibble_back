from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TackleQuery(BaseModel):
    city_id: int | None = None
    category_id: int | None = None
    species_id: int | None = None
    method_id: int | None = None
    limit: int = Field(50, ge=1, le=100)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TackleLinkOut(BaseModel):
    id: int
    category: CategoryOut
    title: str
    url: str
    image_url: str | None
    price_from_rub: int | None
    price_updated_at: datetime | None
    notes: list[str]
