
from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from src.database import all as models  # noqa: F401
from src.settings import settings


@pytest.fixture
def migration_db(monkeypatch):
    name = f"migration_test_{uuid4().hex}"
    connection_args = dict(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
    )
    with psycopg.connect(dbname="postgres", autocommit=True, **connection_args) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        monkeypatch.setattr(settings, "DB_NAME", name)
        try:
            with psycopg.connect(dbname=name, autocommit=True, **connection_args) as db:
                yield db
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


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
