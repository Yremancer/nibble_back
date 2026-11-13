from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx
from src.weather.exceptions import WeatherUnavailableError
from src.weather.models import WeatherCondition

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER = "open-meteo"
COMPASS = ("С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ")


@dataclass(frozen=True)
class CurrentWeather:
    temp_c: Decimal
    condition: WeatherCondition
    wind_dir: str | None
    wind_speed_ms: Decimal | None


@dataclass(frozen=True)
class DayForecast(CurrentWeather):
    forecast_date: date


@dataclass(frozen=True)
class WeatherData:
    current: CurrentWeather
    days: list[DayForecast]


def wmo_to_condition(code: int) -> WeatherCondition:
    if code == 0:
        return WeatherCondition.CLEAR
    if code in (1, 2):
        return WeatherCondition.PARTLY_CLOUDY
    if code == 3:
        return WeatherCondition.CLOUDY
    if code in (45, 48):
        return WeatherCondition.FOG
    if 71 <= code <= 77 or code in (85, 86):
        return WeatherCondition.SNOW
    return WeatherCondition.RAIN


def degrees_to_compass(degrees: float | None) -> str | None:
    return None if degrees is None else COMPASS[round(degrees / 45) % 8]


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(round(value, 1)))


class OpenMeteoClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def fetch(
        self, lat: Decimal, lon: Decimal, timezone: str, days: int
    ) -> WeatherData:
        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "current": "temperature_2m,weather_code,wind_speed_10m,wind_direction_10m",
            "daily": "weather_code,temperature_2m_max,wind_speed_10m_max,wind_direction_10m_dominant",
            "timezone": timezone,
            "forecast_days": days,
            "wind_speed_unit": "ms",
        }
        try:
            response = await self.http.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            body = response.json()
            now, daily = body["current"], body["daily"]
            current = CurrentWeather(
                temp_c=_decimal(now["temperature_2m"]),
                condition=wmo_to_condition(now["weather_code"]),
                wind_dir=degrees_to_compass(now["wind_direction_10m"]),
                wind_speed_ms=_decimal(now["wind_speed_10m"]),
            )
            rows = list(
                zip(
                    daily["time"],
                    daily["weather_code"],
                    daily["temperature_2m_max"],
                    daily["wind_speed_10m_max"],
                    daily["wind_direction_10m_dominant"],
                    strict=True,
                )
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise WeatherUnavailableError() from exc

        forecast = [
            DayForecast(
                forecast_date=date.fromisoformat(day),
                temp_c=_decimal(temp),
                condition=wmo_to_condition(code),
                wind_dir=degrees_to_compass(direction),
                wind_speed_ms=_decimal(speed),
            )
            for day, code, temp, speed, direction in rows
            if code is not None and temp is not None
        ]
        return WeatherData(current=current, days=forecast)
