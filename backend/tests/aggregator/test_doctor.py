from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import telethon

from src.aggregator import doctor
from src.aggregator.cli import main
from src.aggregator.config import AggregatorSettings, SourcesConfig, TelegramSourceConfig


@pytest.fixture
def dependencies(monkeypatch):
    class Session:
        def begin_nested(self):
            return session_context()

        async def execute(self, statement):
            if "alembic_version" in str(statement):
                return SimpleNamespace(scalars=lambda: ["d71a942bc603"])

    @asynccontextmanager
    async def session_context():
        yield Session()

    storage = AsyncMock()
    storage.get.return_value = b"doctor check"

    @asynccontextmanager
    async def storage_context():
        yield storage

    telegram = AsyncMock()
    telegram.is_user_authorized.return_value = True
    classify = AsyncMock(return_value=(SimpleNamespace(decision=SimpleNamespace(value="keep")), None))
    monkeypatch.setattr(doctor, "async_session_maker", session_context)
    monkeypatch.setattr(doctor, "create_storage_client", storage_context)
    monkeypatch.setattr(telethon, "TelegramClient", Mock(return_value=telegram))
    monkeypatch.setattr(doctor, "DeepSeekClient", Mock(return_value=SimpleNamespace(classify_post=classify)))
    monkeypatch.setattr(doctor.aggregator_settings, "TELEGRAM_API_ID", 123)
    monkeypatch.setattr(doctor.aggregator_settings, "TELEGRAM_API_HASH", "test")
    monkeypatch.setattr(doctor.llm_settings, "DEEPSEEK_API_KEY", "test")
    monkeypatch.setattr(doctor.settings, "S3_ACCESS_KEY_ID", "test")
    monkeypatch.setattr(doctor.settings, "S3_SECRET_ACCESS_KEY", "test")
    monkeypatch.setattr(doctor.settings, "S3_BUCKET", "test")
    monkeypatch.setattr(doctor, "load_sources_config", lambda: SourcesConfig(telegram=[
        TelegramSourceConfig(name="one", channel="one"),
        TelegramSourceConfig(name="two", channel="two"),
        TelegramSourceConfig(name="off", channel="off", is_active=False),
    ]))
    return telegram, storage, Session


async def test_doctor_checks_each_active_channel(dependencies):
    telegram, _, _ = dependencies
    assert await doctor.cmd_doctor() == 0
    assert [call.args[0] for call in telegram.get_entity.await_args_list] == ["one", "two"]
    assert telegram.get_messages.await_count == 2
    telegram.disconnect.assert_awaited_once()


@pytest.mark.parametrize("fault", ["channel", "auth", "database", "table", "deepseek", "s3", "s3_content"])
async def test_doctor_returns_failure(dependencies, monkeypatch, fault):
    telegram, storage, session_class = dependencies
    if fault == "channel":
        telegram.get_messages.side_effect = ValueError("not accessible")
    elif fault == "auth":
        telegram.is_user_authorized.return_value = False
    elif fault == "database":
        monkeypatch.setattr(session_class, "execute", AsyncMock(side_effect=OSError))
    elif fault == "table":
        original = session_class.execute

        async def execute(self, statement):
            if "FROM files" in str(statement):
                raise OSError
            return await original(self, statement)

        monkeypatch.setattr(session_class, "execute", execute)
    elif fault == "deepseek":
        monkeypatch.setattr(doctor.llm_settings, "DEEPSEEK_API_KEY", None)
    elif fault == "s3":
        storage.put.side_effect = OSError
    elif fault == "s3_content":
        storage.get.return_value = b"different"
    assert await doctor.cmd_doctor() == 1
    if fault in ("s3", "s3_content"):
        storage.delete.assert_awaited_once()


def test_cli_propagates_doctor_exit_code(monkeypatch):
    from src.aggregator import commands

    monkeypatch.setattr(commands, "cmd_doctor", AsyncMock(return_value=1))
    monkeypatch.setattr("sys.argv", ["aggregator", "doctor"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_session_directory_is_created(tmp_path):
    path = tmp_path / "new" / "telegram.session"
    config = AggregatorSettings(_env_file=None, TELEGRAM_SESSION_PATH=str(path))
    assert config.prepare_telegram_session() == str(path)
    assert path.parent.is_dir()
