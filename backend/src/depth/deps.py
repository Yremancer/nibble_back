from typing import Annotated

from fastapi import Depends
from src.city.repository import CityRepository
from src.database.deps import SessionDep
from src.depth.repository import DepthRepository
from src.depth.service import DepthService


def get_depth_service(session: SessionDep) -> DepthService:
    return DepthService(DepthRepository(session), CityRepository(session))


DepthServiceDep = Annotated[DepthService, Depends(get_depth_service)]
