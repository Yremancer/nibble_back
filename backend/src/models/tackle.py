from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from src.database.base import Base


class TackleCategory(Base):
    __tablename__ = "tackle_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))


class TackleLink(Base):

    __tablename__ = "tackle_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("tackle_categories.id"), index=True
    )
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    price_from_rub: Mapped[int | None] = mapped_column(Integer)
    price_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class TackleRecommendation(Base):
    __tablename__ = "tackle_recommendations"
    __table_args__ = (
        CheckConstraint(
            "species_id IS NOT NULL OR method_id IS NOT NULL", name="has_target"
        ),
        UniqueConstraint(
            "link_id", "species_id", "method_id", postgresql_nulls_not_distinct=True
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    link_id: Mapped[int] = mapped_column(
        ForeignKey("tackle_links.id", ondelete="CASCADE")
    )
    species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="CASCADE"), index=True
    )
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("fishing_methods.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(255))
