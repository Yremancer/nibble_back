from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from src.auth.exceptions import AuthenticationError
from src.auth.models import AuthSession
from src.auth.repository import AuthSessionRepository
from src.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from src.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from src.settings import settings
from src.user.models import User
from src.user.service import UserService


class AuthTokens(NamedTuple):
    token: TokenResponse
    refresh_token: str
    expires_at: datetime


class AuthService:
    def __init__(self, users: UserService, sessions: AuthSessionRepository):
        self._users = users
        self._sessions = sessions

    async def register(self, data: RegisterRequest) -> User:
        return await self._users.create(
            email=str(data.email),
            password_hash=await hash_password(data.password.get_secret_value()),
            display_name=data.display_name,
            city_id=data.city_id,
        )

    async def login(self, data: LoginRequest) -> AuthTokens:
        user = await self._users.get_by_email(str(data.email))
        hashed = user.password_hash if user is not None else None
        valid = await verify_password(data.password.get_secret_value(), hashed)
        if user is None or not valid:
            raise AuthenticationError
        now = datetime.now(UTC)
        await self._sessions.delete_expired(now)
        refresh_token = create_refresh_token()
        session = await self._sessions.add(
            AuthSession(
                user_id=user.id,
                refresh_token_hash=hash_refresh_token(refresh_token),
                expires_at=now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        return self._tokens(session, refresh_token)

    async def refresh(self, token: str | None) -> AuthTokens:
        if not token:
            raise AuthenticationError
        session = await self._sessions.get_for_refresh(hash_refresh_token(token))
        if session is None or session.expires_at <= datetime.now(UTC):
            raise AuthenticationError
        if await self._users.get_by_id(session.user_id) is None:
            raise AuthenticationError
        refresh_token = create_refresh_token()
        await self._sessions.rotate(session, hash_refresh_token(refresh_token))
        return self._tokens(session, refresh_token)

    async def logout(self, token: str | None) -> None:
        if token:
            await self._sessions.revoke(hash_refresh_token(token))

    @staticmethod
    def _tokens(session: AuthSession, refresh_token: str) -> AuthTokens:
        return AuthTokens(
            token=TokenResponse(
                access_token=create_access_token(session.user_id, session.id),
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
            refresh_token=refresh_token,
            expires_at=session.expires_at,
        )

    async def current_user(self, token: str) -> User:
        user_id, session_id = decode_access_token(token)
        session = await self._sessions.get(session_id)
        if (
            session is None
            or session.user_id != user_id
            or session.expires_at <= datetime.now(UTC)
        ):
            raise AuthenticationError
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise AuthenticationError
        return user
