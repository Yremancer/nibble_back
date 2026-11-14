from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import AuthSession


class AuthSessionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, session_id: UUID) -> AuthSession | None:
        return await self._session.get(AuthSession, session_id)

    async def get_for_refresh(self, token_hash: str) -> AuthSession | None:
        return await self._session.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == token_hash)
            .with_for_update()
        )

    async def add(self, session: AuthSession) -> AuthSession:
        self._session.add(session)
        await self._session.flush()
        return session

    async def rotate(self, session: AuthSession, token_hash: str) -> None:
        session.refresh_token_hash = token_hash
        await self._session.flush()

    async def revoke(self, token_hash: str) -> None:
        await self._session.execute(
            delete(AuthSession).where(AuthSession.refresh_token_hash == token_hash)
        )

    async def delete_expired(self, now: datetime) -> None:
        await self._session.execute(
            delete(AuthSession).where(AuthSession.expires_at <= now)
        )
