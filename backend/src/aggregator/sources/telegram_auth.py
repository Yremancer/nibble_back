
from telethon import TelegramClient
from src.aggregator.config import aggregator_settings


async def run_telegram_auth() -> None:
    if not aggregator_settings.is_telegram_configured:
        raise RuntimeError(
            "TELEGRAM_API_ID/TELEGRAM_API_HASH не заданы в .env"
        )

    client = TelegramClient(
        aggregator_settings.TELEGRAM_SESSION_PATH,
        aggregator_settings.TELEGRAM_API_ID,
        aggregator_settings.TELEGRAM_API_HASH,
    )
    await client.start(phone=lambda: aggregator_settings.TELEGRAM_PHONE or input("Телефон: "))
    me = await client.get_me()
    print(f"Авторизован как {me.first_name} ({me.phone}). Сессия сохранена.")
    await client.disconnect()
