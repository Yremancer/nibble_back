import asyncio
from uuid import uuid4

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text

from src.aggregator.config import aggregator_settings, load_sources_config
from src.aggregator import models as aggregator_models  # noqa: F401
from src.database.all import *  # noqa: F403 - registers domain tables
from src.database.base import Base
from src.database.database import async_session_maker
from src.llm.client import DeepSeekClient
from src.llm.settings import llm_settings
from src.settings import settings
from src.storage.setup import create_storage_client


async def cmd_doctor() -> int:
    print("=== Диагностика агрегатора: БД, Telegram, DeepSeek, S3 ===")
    failures = 0

    def fail(component: str, detail: str) -> None:
        nonlocal failures
        failures += 1
        print(f"[FAIL] {component}: {detail}")

    try:
        async with async_session_maker() as session:
            heads = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
            current = set((await session.execute(text("SELECT version_num FROM alembic_version"))).scalars())
            if current != heads:
                fail("Миграции", "БД не на head; выполните make update-db")
            else:
                print("[OK] Миграции: БД на head")
            for table in Base.metadata.sorted_tables:
                try:
                    async with session.begin_nested():
                        await session.execute(select(table).limit(0))
                except Exception:  # noqa: BLE001
                    fail(f"Таблица {table.name}", "недоступна или не соответствует модели")
            print("[OK] PostgreSQL: подключение работает, проверка таблиц завершена")
    except Exception as exc:  # noqa: BLE001
        fail("PostgreSQL", f"{type(exc).__name__}; проверьте подключение и make update-db")

    try:
        channels = [source for source in load_sources_config().telegram if source.is_active]
    except Exception as exc:  # noqa: BLE001
        fail("sources.json", type(exc).__name__)
        channels = []

    if not channels:
        print("[SKIP] Telegram: нет активных каналов в sources.json")
    elif not aggregator_settings.is_telegram_configured:
        from src.aggregator.sources.telegram_public import PublicTelegramCollector

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            for source in channels:
                try:
                    collector = PublicTelegramCollector(client, source.channel)
                    await collector.resolve_channel_id()
                    async for _ in collector.iter_history(reverse=True):
                        break
                    print(f"[OK] Telegram {source.channel}: веб-превью доступно без API credentials")
                except Exception as exc:  # noqa: BLE001
                    fail(f"Telegram {source.channel}", f"веб-превью недоступно ({type(exc).__name__}); нужен открытый канал с username")
    else:
        from telethon import TelegramClient

        client = None
        try:
            client = TelegramClient(
                aggregator_settings.prepare_telegram_session(),
                aggregator_settings.TELEGRAM_API_ID,
                aggregator_settings.TELEGRAM_API_HASH,
            )
            async with asyncio.timeout(30):
                await client.connect()
                authorized = await client.is_user_authorized()
            if not authorized:
                fail("Telegram", "сессия не авторизована; выполните auth-telegram")
            else:
                print("[OK] Telegram: сессия авторизована")
                for source in channels:
                    try:
                        async with asyncio.timeout(30):
                            entity = await client.get_entity(source.channel)
                            await client.get_messages(entity, limit=1)
                        print(f"[OK] Telegram {source.channel}: история доступна")
                    except Exception as exc:  # noqa: BLE001
                        fail(f"Telegram {source.channel}", f"история недоступна ({type(exc).__name__}); проверьте имя и доступ аккаунта")
        except Exception as exc:  # noqa: BLE001
            fail("Telegram", f"{type(exc).__name__}; проверьте API credentials, сессию и сеть")
        finally:
            if client is not None:
                await client.disconnect()

    if not llm_settings.is_configured:
        fail("DeepSeek", "задайте DEEPSEEK_API_KEY; классификация недоступна")
    else:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as http_client:
                client = DeepSeekClient(llm_settings, http_client)
                result, _ = await client.classify_post(
                    'Ответь JSON: {"decision": "keep", "reason": "ping", '
                    '"is_advertisement": false, "needs_media_analysis": false}',
                    "ping",
                )
                print(f"[OK] DeepSeek: ответ получен, decision={result.decision.value}")
        except Exception as exc:  # noqa: BLE001
            fail("DeepSeek", f"{type(exc).__name__}; проверьте ключ, модель, квоту и доступ к API")

    if not (settings.S3_BUCKET and settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY):
        fail("S3", "задайте S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY")
    else:
        try:
            async with create_storage_client() as client:
                test_key = f"aggregator-doctor/{uuid4().hex}.txt"
                try:
                    await client.put(test_key, b"doctor check", content_type="text/plain")
                    if await client.get(test_key) != b"doctor check":
                        raise RuntimeError("S3 returned different content")
                finally:
                    await client.delete(test_key)
            print("[OK] S3: тестовая запись/чтение/удаление успешны")
        except Exception as exc:  # noqa: BLE001
            fail("S3", f"{type(exc).__name__}; проверьте endpoint, bucket, ключи и права на объекты")

    print(f"Диагностика завершена: обязательных неисправностей — {failures}")
    return 1 if failures else 0
