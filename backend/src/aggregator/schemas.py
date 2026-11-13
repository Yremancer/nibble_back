from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class TelegramMediaPreview(BaseModel):
    url: str
    media_type: Literal["photo", "video"]


class TelegramPostPreview(BaseModel):
    external_id: str
    all_message_ids: list[int]
    text: str
    published_at: datetime
    original_url: str
    media: list[TelegramMediaPreview]
    reactions_count: int | None
    comments_count: int | None
    forwarded_from_url: str | None
