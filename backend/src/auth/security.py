import asyncio
from datetime import UTC, datetime, timedelta

import jwt
from argon2.exceptions import InvalidHashError, VerificationError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from src.auth.constants import (
    JWT_ACCESS_TOKEN_TYPE,
    JWT_ALGORITHM,
    JWT_REQUIRED_CLAIMS,
)
from src.auth.exceptions import AuthenticationError
from src.settings import settings

_PASSWORD_HASHER = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash("not-a-user-password")


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_PASSWORD_HASHER.hash, password)


async def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return await asyncio.to_thread(
            _PASSWORD_HASHER.verify, password, hashed or _DUMMY_PASSWORD_HASH
        )
    except (UnknownHashError, InvalidHashError, VerificationError):
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
            "type": JWT_ACCESS_TOKEN_TYPE,
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": JWT_REQUIRED_CLAIMS},
        )
        user_id = int(payload["sub"])
        if payload["type"] != JWT_ACCESS_TOKEN_TYPE:
            raise AuthenticationError
        return user_id
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise AuthenticationError from exc
