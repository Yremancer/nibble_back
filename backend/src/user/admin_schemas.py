from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
)
from src.settings import settings
from src.user.models import UserRole


class AdminUserQuery(BaseModel):
    role: UserRole | None = None
    q: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    cursor: int | None = Field(None, ge=1)
    limit: int = Field(20, ge=1, le=100)


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=settings.AUTH_PASSWORD_MIN_LENGTH)
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    city_id: int
    role: UserRole = UserRole.USER


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str
    city_id: int
    role: UserRole
    avatar_url: str | None
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    next_cursor: int | None
