from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column
from src.database.base import Base


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)
    original_name: Mapped[str]
    content_type: Mapped[str]
    size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
