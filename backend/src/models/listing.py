from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check


class ListingState(StrEnum):
    """Достоверное состояние карточки, отдельно от listings.is_active:
    403/отсутствие в обходе не означает снятие объявления."""

    ACTIVE = "active"
    REMOVED = "removed"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class ListingMediaType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"


class Listing(Base):
    """Объявление Фарпоста (per-ad). Расширение модели из PDF: в коде
    проекта до этой задачи существовал только tackle_links (ссылка на
    отфильтрованную выдачу), а не карточка конкретного товара."""

    __tablename__ = "listings"
    __table_args__ = (
        enum_check("state", ListingState),
        Index(
            "ix_listings_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    farpost_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("tackle_categories.id", ondelete="SET NULL"), index=True
    )
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    price_rub: Mapped[int | None] = mapped_column(Integer)
    price_raw: Mapped[str | None] = mapped_column(String(100))
    """Исходное представление цены: 'договорная', дробные значения и т.п.,
    когда price_rub (int) не может хранить его молча округлённым."""
    photo_url: Mapped[str | None] = mapped_column(Text)
    """Главное фото для совместимости с полем listings.photo_url из PDF."""
    url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    state: Mapped[str] = mapped_column(
        String(20), server_default=sql_text("'unknown'")
    )
    seller_name: Mapped[str | None] = mapped_column(String(255))
    seller_url: Mapped[str | None] = mapped_column(Text)
    characteristics: Mapped[dict | None] = mapped_column(JSONB)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Когда карточка последний раз подтверждена доступной в обходе."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    media: Mapped[list["ListingMedia"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ListingMedia.sort_order",
    )
    price_history: Mapped[list["ListingPriceHistory"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ListingPriceHistory.recorded_at",
    )


class ListingMedia(Base):
    __tablename__ = "listing_media"
    __table_args__ = (
        enum_check("type", ListingMediaType),
        UniqueConstraint("listing_id", "media_file_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    media_file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[str] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=sql_text("0"))


class ListingPriceHistory(Base):
    __tablename__ = "listing_price_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    price_rub: Mapped[int | None] = mapped_column(Integer)
    price_raw: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ListingRecommendation(Base):
    __tablename__ = "listing_recommendations"
    __table_args__ = (
        CheckConstraint(
            "species_id IS NOT NULL OR method_id IS NOT NULL", name="has_target"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    species_id: Mapped[int | None] = mapped_column(
        ForeignKey("species.id", ondelete="CASCADE"), index=True
    )
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("fishing_methods.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[str | None] = mapped_column(String(255))
