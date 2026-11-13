from typing import Annotated

from fastapi import Depends
from src.city.repository import CityRepository
from src.city.service import CityService
from src.database.deps import SessionDep


def get_city_service(session: SessionDep) -> CityService:
    return CityService(CityRepository(session))


CityServiceDep = Annotated[CityService, Depends(get_city_service)]
