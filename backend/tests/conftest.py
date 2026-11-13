"""Тестовая сессия БД: каждый тест выполняется в транзакции, которая
откатывается после теста (используется уже применённая миграция реальной
dev-базы, без отдельной тестовой БД — см. ponytail: не плодить
инфраструктуру ради тестов).

Движок создаётся заново в каждом тесте с NullPool: пул asyncpg привязан к
event loop, а pytest-asyncio создаёт новый loop на каждый тест."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from src.models import *  # noqa: F401,F403 - регистрирует все ORM-модели
from src.settings import settings


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        trans = await connection.begin()
        async_session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield async_session
        finally:
            await async_session.close()
            await trans.rollback()
    await engine.dispose()
