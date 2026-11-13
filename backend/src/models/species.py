from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from src.database.base import Base, enum_check
from src.species.models import FishingMethod, Species, SpeciesMonth

__all__ = [
    "FishingMethod",
    "Species",
    "SpeciesMonth",
    "SpotMethod",
    "SpotSpecies",
    "SpotSpeciesSource",
]


class SpotSpeciesSource(StrEnum):
    OPEN_SOURCES = "open_sources"
    REPORTS = "reports"
    MODERATOR = "moderator"


class SpotSpecies(Base):
    __tablename__ = "spot_species"
    __table_args__ = (enum_check("data_source", SpotSpeciesSource),)

    spot_id: Mapped[int] = mapped_column(
        ForeignKey("spots.id", ondelete="CASCADE"), primary_key=True
    )
    species_id: Mapped[int] = mapped_column(
        ForeignKey("species.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    data_source: Mapped[str | None] = mapped_column(String(20))


class SpotMethod(Base):
    __tablename__ = "spot_methods"

    spot_id: Mapped[int] = mapped_column(
        ForeignKey("spots.id", ondelete="CASCADE"), primary_key=True
    )
    method_id: Mapped[int] = mapped_column(
        ForeignKey("fishing_methods.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
