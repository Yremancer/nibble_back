from typing import Annotated

from fastapi import APIRouter, Query
from src.aggregator.deps import FarpostServiceDep
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
