from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check


class MediaType(StrEnum):
    PHOTO = "photo"
    VIDEO = "video"


class MediaUploadState(StrEnum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    FAILED = "failed"


class MediaFile(Base):
    """Файл в S3: один объект может использоваться несколькими публикациями/объявлениями."""

    __tablename__ = "media_files"
    __table_args__ = (enum_check("upload_state", MediaUploadState),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(100))
    object_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    preview_object_key: Mapped[str | None] = mapped_column(Text)
    upload_state: Mapped[str] = mapped_column(
        String(20), server_default=sql_text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
        ForeignKey("media_files.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[str] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default=sql_text("0"))

    media_file: Mapped["MediaFile"] = relationship()
