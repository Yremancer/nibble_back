from typing import Annotated

from fastapi import APIRouter, Query
from src.aggregator.deps import FarpostServiceDep, TelegramServiceDep
from src.aggregator.schemas import TelegramPostPreview
from src.aggregator.sources.farpost_collector import ListingDetail

router = APIRouter(prefix="/aggregator", tags=["aggregator"])


@router.get(
    "/farpost",
    response_model=list[ListingDetail],
    summary="Получить объявления Farpost",
    description=(
        "Загружает до limit объявлений из настроенного раздела Farpost, начиная с первой страницы. "
        "Возвращает полные карточки и исходные ссылки на фото. "
        "Не сохраняет данные в БД и не загружает файлы в S3. "
        "Если объявлений меньше запрошенного количества, список будет короче."
    ),
    responses={502: {"description": "Farpost недоступен или вернул ошибку"}},
)
async def preview_farpost(
    service: FarpostServiceDep,
    limit: Annotated[int, Query(ge=1, le=50, description="Количество объявлений (от 1 до 50)")] = 5,
):
    return await service.preview(limit)


@router.get(
    "/telegram",
    response_model=list[TelegramPostPreview],
    summary="Получить публикации Telegram для тестирования",
    description=(
        "Загружает до limit последних публикаций публичного канала, от новых к старым, без ключей Telegram API. "
        "Возвращает текст, дату, ссылку на пост и доступные в веб-превью ссылки на фото/видео. "
        "Альбом считается одной публикацией. Не сохраняет данные в БД и не загружает файлы в S3. "
        "Если доступных публикаций меньше запрошенного количества, список будет короче."
    ),
    responses={502: {"description": "Telegram недоступен или веб-превью канала не поддерживается"}},
)
async def preview_telegram(
    service: TelegramServiceDep,
    limit: Annotated[int, Query(ge=1, le=50, description="Количество публикаций (от 1 до 50)")] = 5,
):
    return await service.preview(limit)
