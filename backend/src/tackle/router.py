from typing import Annotated

from fastapi import APIRouter, Query
from src.tackle.deps import TackleServiceDep
from src.tackle.schemas import CategoryOut, TackleLinkOut, TackleQuery

router = APIRouter(prefix="/tackle", tags=["tackle"])


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(service: TackleServiceDep):
    return await service.list_categories()


@router.get(
    "",
    response_model=list[TackleLinkOut],
    description=(
        "Подборка ссылок на Farpost. species_id и method_id работают вместе: "
        "найдутся подборки под эту рыбу, под этот способ и под эту пару."
    ),
)
async def list_tackle(
    query: Annotated[TackleQuery, Query()], service: TackleServiceDep
):
    return await service.list_links(query)
