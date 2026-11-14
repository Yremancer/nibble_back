from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)
from src.user.models import UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    city_id: int
    role: UserRole
    avatar_url: str | None
    bio: str | None
    created_at: datetime


class CityRef(BaseModel):
    id: int
    name: str


class ProfileOut(BaseModel):
    """Публичный профиль: без email и роли."""

    id: int
    display_name: str
    avatar_url: str | None
    bio: str | None
    city: CityRef
    created_at: datetime
    posts_count: int
    followers_count: int
    following_count: int
    is_following: bool
    is_me: bool


class UserBrief(BaseModel):
    id: int
    display_name: str
    avatar_url: str | None
    is_following: bool


class UserPage(BaseModel):
    items: list[UserBrief]
    next_cursor: str | None


class FollowListQuery(BaseModel):
    cursor: str | None = None
    limit: int = Field(20, ge=1, le=100)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    display_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None
    ) = None
    city_id: int | None = None
    avatar_url: str | None = None
    bio: str | None = None
    role: UserRole | None = None

    @field_validator("email", "display_name", "city_id", "role")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Field cannot be null")
        return value
