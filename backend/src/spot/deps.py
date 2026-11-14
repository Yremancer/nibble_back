from typing import Annotated

from fastapi import Depends
from src.city.repository import CityRepository
from src.database.deps import SessionDep
from src.species.repository import SpeciesRepository
from src.spot.admin_service import SpotAdminService
from src.spot.repository import SpotRepository
from src.spot.service import SpotService


def get_spot_service(session: SessionDep) -> SpotService:
    return SpotService(SpotRepository(session))


SpotServiceDep = Annotated[SpotService, Depends(get_spot_service)]


def get_spot_admin_service(session: SessionDep) -> SpotAdminService:
    return SpotAdminService(
        SpotRepository(session), CityRepository(session), SpeciesRepository(session)
    )


SpotAdminServiceDep = Annotated[SpotAdminService, Depends(get_spot_admin_service)]
