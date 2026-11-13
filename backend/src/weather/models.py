from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from src.database.base import Base, enum_check


class WeatherCondition(StrEnum):
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    RAIN = "rain"
    SNOW = "snow"
    FOG = "fog"


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"
    __table_args__ = (
        CheckConstraint("(city_id IS NULL) <> (spot_id IS NULL)", name="one_target"),
        enum_check("condition", WeatherCondition),
        UniqueConstraint("city_id", "forecast_date"),
        UniqueConstraint("spot_id", "forecast_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE")
    )
    spot_id: Mapped[int | None] = mapped_column(
        ForeignKey("spots.id", ondelete="CASCADE")
    )
    forecast_date: Mapped[date] = mapped_column(Date)
    temp_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    condition: Mapped[str] = mapped_column(String(20))
    wind_dir: Mapped[str | None] = mapped_column(String(3))
    wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    provider: Mapped[str] = mapped_column(String(50))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WeatherCurrent(Base):
    __tablename__ = "weather_current"
    __table_args__ = (
        CheckConstraint("(city_id IS NULL) <> (spot_id IS NULL)", name="one_target"),
        enum_check("condition", WeatherCondition),
        UniqueConstraint("city_id"),
        UniqueConstraint("spot_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="CASCADE")
    )
    spot_id: Mapped[int | None] = mapped_column(
        ForeignKey("spots.id", ondelete="CASCADE")
    )
    temp_c: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    condition: Mapped[str] = mapped_column(String(20))
    wind_dir: Mapped[str | None] = mapped_column(String(3))
    wind_speed_ms: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    provider: Mapped[str] = mapped_column(String(50))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
