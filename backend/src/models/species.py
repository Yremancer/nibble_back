from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check


class SpotSpeciesSource(StrEnum):
    OPEN_SOURCES = "open_sources"
    REPORTS = "reports"
    MODERATOR = "moderator"


class Species(Base):
    __tablename__ = "species"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    latin_name: Mapped[str | None] = mapped_column(String(150))
    short_description: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    identification: Mapped[str | None] = mapped_column(Text)
    typical_length_cm: Mapped[int | None] = mapped_column(SmallInteger)
    typical_weight_g: Mapped[int | None] = mapped_column(Integer)
    image_url: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)))
    """Альтернативные названия для словарного сопоставления импортированных
    упоминаний вида (см. открытый вопрос в PDF, раздел 5)."""

    months: Mapped[list["SpeciesMonth"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SpeciesMonth.month",
    )


class SpeciesMonth(Base):
    __tablename__ = "species_months"
    __table_args__ = (CheckConstraint("month BETWEEN 1 AND 12", name="month"),)

    species_id: Mapped[int] = mapped_column(
        ForeignKey("species.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[int] = mapped_column(SmallInteger, primary_key=True, index=True)


class FishingMethod(Base):
    __tablename__ = "fishing_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


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
