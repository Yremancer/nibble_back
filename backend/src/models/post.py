from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check


class SourceType(StrEnum):
    KLEV = "klev"
    TELEGRAM = "telegram"
    VK = "vk"


class PostStatus(StrEnum):
    PUBLISHED = "published"
    HIDDEN = "hidden"
    MODERATION = "moderation"


class PostKind(StrEnum):

    FISHING_REPORT = "fishing_report"
    INCIDENT = "incident"
    USEFUL_INFO = "useful_info"


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (enum_check("type", SourceType),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(150))
    url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(100))
    city_id: Mapped[int | None] = mapped_column(
        ForeignKey("cities.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        enum_check("status", PostStatus),
        enum_check("kind", PostKind),
        UniqueConstraint("source_id", "external_post_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    spot_id: Mapped[int | None] = mapped_column(
        ForeignKey("spots.id", ondelete="SET NULL"), index=True
    )
    method_id: Mapped[int | None] = mapped_column(
        ForeignKey("fishing_methods.id", ondelete="SET NULL")
    )
    text: Mapped[str] = mapped_column(Text)
    bait: Mapped[str | None] = mapped_column(String(255))
    conditions: Mapped[str | None] = mapped_column(Text)
    fishing_date: Mapped[date | None] = mapped_column(Date)
    show_spot: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    show_date: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    external_post_id: Mapped[str | None] = mapped_column(String(100))
    original_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), server_default=sql_text("'published'")
    )
    likes_count: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    comments_count: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    kind: Mapped[str] = mapped_column(
        String(20), server_default=sql_text("'fishing_report'")
    )

    event_date: Mapped[date | None] = mapped_column(Date)

    tg_reactions_count: Mapped[int | None] = mapped_column(Integer)
    tg_comments_count: Mapped[int | None] = mapped_column(Integer)

    canonical_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), index=True
    )

    managed_fields: Mapped[dict | None] = mapped_column(JSONB)

    source: Mapped["Source"] = relationship()
    author: Mapped["User | None"] = relationship()  # noqa: F821
    spot: Mapped["Spot | None"] = relationship()  # noqa: F821
    media: Mapped[list["PostMedia"]] = relationship(  # noqa: F821
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PostMedia.sort_order",
    )
    catches: Mapped[list["PostSpecies"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class PostSpecies(Base):
    __tablename__ = "post_species"

    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    species_id: Mapped[int] = mapped_column(
        ForeignKey("species.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    quantity: Mapped[int | None] = mapped_column(SmallInteger)
    max_weight_g: Mapped[int | None] = mapped_column(Integer)


class PostLike(Base):
    __tablename__ = "post_likes"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
