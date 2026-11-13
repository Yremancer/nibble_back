from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator
from src.weather.models import WeatherCondition


class WeatherQuery(BaseModel):
    city_id: int | None = None
    spot_id: int | None = None

    @model_validator(mode="after")
    def check_one_target(self) -> "WeatherQuery":
        if (self.city_id is None) == (self.spot_id is None):
            raise ValueError("Pass exactly one of city_id or spot_id")
        return self


class WeatherNow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    temp_c: float
    condition: WeatherCondition
    wind_dir: str | None
    wind_speed_ms: float | None


class WeatherDay(WeatherNow):
    forecast_date: date


class WeatherResponse(BaseModel):
    name: str
    city_id: int | None
    spot_id: int | None
    fetched_at: datetime | None
    current: WeatherNow | None
    days: list[WeatherDay]
