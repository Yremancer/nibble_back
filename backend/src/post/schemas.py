from datetime import date, datetime

from pydantic import BaseModel, Field
from src.models.media import MediaType
from src.models.post import PostKind, SourceType


class FeedQuery(BaseModel):
    city_id: int | None = None
    source: SourceType | None = None
    spot_id: int | None = None
    species_id: int | None = None
    kind: PostKind | None = None
    cursor: str | None = None
    limit: int = Field(20, ge=1, le=50)


class SourceOut(BaseModel):
    id: int
    type: SourceType
    name: str
    url: str | None


class AuthorOut(BaseModel):
    id: int
    display_name: str
    avatar_url: str | None


class SpotRef(BaseModel):
    id: int
    name: str


class MethodRef(BaseModel):
    id: int
    name: str


class CatchOut(BaseModel):
    id: int
    name: str
    quantity: int | None
    max_weight_g: int | None


class MediaOut(BaseModel):
    type: MediaType
    url: str


class PostOut(BaseModel):
    id: int
    kind: PostKind
    text: str
    bait: str | None
    conditions: str | None
    published_at: datetime
    fishing_date: date | None
    event_date: date | None
    source: SourceOut
    author: AuthorOut | None
    spot: SpotRef | None
    method: MethodRef | None
    species: list[CatchOut]
    media: list[MediaOut]
    likes_count: int
    comments_count: int
    tg_reactions_count: int | None
    tg_comments_count: int | None
    original_url: str | None


class PostPage(BaseModel):
    items: list[PostOut]
    next_cursor: str | None
