from typing import Annotated

from fastapi import Depends, Query, Request
from src.aggregator.config import aggregator_settings
from src.aggregator.service import FarpostService, TelegramService
from src.aggregator.sources.farpost_collector import FarpostCollector
from src.aggregator.sources.telegram_public import PublicTelegramCollector


def get_farpost_service(request: Request) -> FarpostService:
    return FarpostService(FarpostCollector(
        request.app.state.http,
        aggregator_settings.FARPOST_BASE_URL,
        aggregator_settings.FARPOST_CITY_PATH,
    ))


FarpostServiceDep = Annotated[FarpostService, Depends(get_farpost_service)]


def get_telegram_service(
    request: Request,
    channel: Annotated[str, Query(pattern=r"^[A-Za-z][A-Za-z0-9_]*$", max_length=32,
                                  description="Username публичного канала без @ и ссылки")],
) -> TelegramService:
    return TelegramService(PublicTelegramCollector(request.app.state.http, channel))


TelegramServiceDep = Annotated[TelegramService, Depends(get_telegram_service)]
