from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from src.city.models import City
from src.database.base import Base
from src.spot.models import Spot

__all__ = ["City", "DepthLayer", "Spot"]


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
