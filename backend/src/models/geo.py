from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check


class WeatherCondition(StrEnum):
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    RAIN = "rain"
    SNOW = "snow"
    FOG = "fog"


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    timezone: Mapped[str] = mapped_column(String(50))


class Spot(Base):
    __tablename__ = "spots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    area: Mapped[str | None] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    photo_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    species: Mapped[list["SpotSpecies"]] = relationship(  # noqa: F821
        cascade="all, delete-orphan", passive_deletes=True
    )
    methods: Mapped[list["SpotMethod"]] = relationship(  # noqa: F821
        cascade="all, delete-orphan", passive_deletes=True
    )


class DepthLayer(Base):
    __tablename__ = "depth_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    tile_url_template: Mapped[str] = mapped_column(Text)
    attribution: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
