from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.database.base import Base


class DepthLayer(Base):
    """Зона глубин города: GeoJSON MultiPolygon от depth_from до depth_to метров."""

    __tablename__ = "depth_layers"
    __table_args__ = (
        UniqueConstraint("city_id", "depth_from"),
        CheckConstraint(
            "depth_from >= 0 AND (depth_to IS NULL OR depth_to > depth_from)",
            name="depth_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    depth_from: Mapped[int] = mapped_column(SmallInteger)
    depth_to: Mapped[int | None] = mapped_column(SmallInteger)
    geometry: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attribution: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
