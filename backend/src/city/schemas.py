from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    lat: Decimal
    lon: Decimal
    timezone: str
