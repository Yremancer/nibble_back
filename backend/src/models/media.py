from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check
from src.storage.models import File


class MediaType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"


class PostMedia(Base):
    """Фото и видео публикации в едином порядке."""

    __tablename__ = "post_media"
    __table_args__ = (
        enum_check("type", MediaType),
        UniqueConstraint("post_id", "media_file_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    media_file_id: Mapped[int] = mapped_column(
        ForeignKey("files.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[str] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=sql_text("0"))

    media_file: Mapped["File"] = relationship()
