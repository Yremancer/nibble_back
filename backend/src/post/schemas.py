from datetime import date, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from src.models.media import MediaType
from src.post.models import PostKind, SourceType

PostText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]
MediaKeys = Annotated[list[str], Field(min_length=1, max_length=10)]


def _check_unique(values: list, what: str) -> list:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} must not repeat")
    return values


class FeedQuery(BaseModel):
    city_id: int | None = None
    source: SourceType | None = None
    spot_id: int | None = None
    species_id: int | None = None
    kind: PostKind | None = None
    author_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    following: bool = False
    cursor: str | None = None
    limit: int = Field(20, ge=1, le=50)

    @model_validator(mode="after")
    def _date_range(self) -> "FeedQuery":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be later than date_to")
        return self


class CatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    species_id: int
    quantity: int | None = Field(None, gt=0, le=32767)
    max_weight_g: int | None = Field(None, gt=0, le=2_000_000_000)


class PostFields(BaseModel):

    model_config = ConfigDict(extra="forbid")

    spot_id: int | None = None
    method_id: int | None = None
    bait: Annotated[str, StringConstraints(max_length=255)] | None = None
    conditions: Annotated[str, StringConstraints(max_length=2000)] | None = None
    fishing_date: date | None = None


class PostCreate(PostFields):
    text: PostText
    media: MediaKeys
    species: list[CatchIn] = Field(default_factory=list, max_length=10)
    show_spot: bool = True
    show_date: bool = True

    @field_validator("media")
    @classmethod
    def _media_unique(cls, value: list[str]) -> list[str]:
        return _check_unique(value, "media")

    @field_validator("species")
    @classmethod
    def _species_unique(cls, value: list[CatchIn]) -> list[CatchIn]:
        _check_unique([c.species_id for c in value], "species")
        return value


class PostUpdate(PostFields):

    text: PostText | None = Field(None)
    media: MediaKeys | None = None
    species: list[CatchIn] | None = Field(None, max_length=10)
    show_spot: bool | None = None
    show_date: bool | None = None

    @field_validator("text", "show_spot", "show_date", "media", "species")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("must not be null")
        return value

    @field_validator("media")
    @classmethod
    def _media_unique(cls, value: list[str]) -> list[str]:
        return _check_unique(value, "media")

    @field_validator("species")
    @classmethod
    def _species_unique(cls, value: list[CatchIn]) -> list[CatchIn]:
        _check_unique([c.species_id for c in value], "species")
        return value


class SourceOut(BaseModel):
    id: int
    type: SourceType
    name: str
    url: str | None


class AuthorOut(BaseModel):
    id: int
    display_name: str
    avatar_url: str | None


class PostAuthorOut(AuthorOut):
    is_following: bool


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
    author: PostAuthorOut | None
    spot: SpotRef | None
    method: MethodRef | None
    species: list[CatchOut]
    media: list[MediaOut]
    likes_count: int
    liked_by_me: bool
    comments_count: int
    tg_reactions_count: int | None
    tg_comments_count: int | None
    original_url: str | None


class PostPage(BaseModel):
    items: list[PostOut]
    next_cursor: str | None


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: PostText
    parent_id: int | None = None


class CommentOut(BaseModel):
    id: int
    post_id: int
    parent_id: int | None
    text: str
    author: AuthorOut
    created_at: datetime


class CommentPage(BaseModel):
    items: list[CommentOut]
    next_cursor: int | None
