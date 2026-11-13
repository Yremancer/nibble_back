from typing import Annotated

from fastapi import Depends, Request
from src.aggregator.config import aggregator_settings
from src.aggregator.service import FarpostService
from src.aggregator.sources.farpost_collector import FarpostCollector


def get_farpost_service(request: Request) -> FarpostService:
    return FarpostService(FarpostCollector(
        request.app.state.http,
        aggregator_settings.FARPOST_BASE_URL,
        aggregator_settings.FARPOST_CITY_PATH,
    ))


FarpostServiceDep = Annotated[FarpostService, Depends(get_farpost_service)]
