from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check


class SpotSpeciesSource(StrEnum):
    OPEN_SOURCES = "open_sources"
    REPORTS = "reports"
    MODERATOR = "moderator"


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

    species: Mapped[list["SpotSpecies"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    methods: Mapped[list["SpotMethod"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


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
