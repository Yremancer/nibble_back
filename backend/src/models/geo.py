from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.city.models import City
from src.database.base import Base

__all__ = ["City", "DepthLayer", "Spot"]


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
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String(150)))
    """Альтернативные названия для словарного сопоставления импортированных
    упоминаний места (см. открытый вопрос в PDF, раздел 5)."""

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
