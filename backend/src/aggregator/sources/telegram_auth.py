"""Первичная авторизация Telegram-сессии (отдельная команда `auth telegram`).

Код/пароль 2FA вводятся интерактивно в терминале и никогда не логируются.
Файл сессии хранится локально по TELEGRAM_SESSION_PATH (не в git — путь по
умолчанию вне репозитория/в volume)."""

from telethon import TelegramClient
from src.aggregator.config import aggregator_settings


async def run_telegram_auth() -> None:
    if not aggregator_settings.is_telegram_configured:
        raise RuntimeError(
            "TELEGRAM_API_ID/TELEGRAM_API_HASH не заданы в .env"
        )

    client = TelegramClient(
        aggregator_settings.prepare_telegram_session(),
        aggregator_settings.TELEGRAM_API_ID,
        aggregator_settings.TELEGRAM_API_HASH,
    )
    try:
        await client.start(phone=lambda: aggregator_settings.TELEGRAM_PHONE or input("Телефон: "))
        me = await client.get_me()
        print(f"Авторизован как {me.first_name} ({me.phone}). Сессия сохранена.")
    finally:
        await client.disconnect()
