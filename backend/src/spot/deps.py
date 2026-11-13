from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.spot.repository import SpotRepository
from src.spot.service import SpotService


def get_spot_service(session: SessionDep) -> SpotService:
    return SpotService(SpotRepository(session))


SpotServiceDep = Annotated[SpotService, Depends(get_spot_service)]
