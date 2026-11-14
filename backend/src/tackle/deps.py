from typing import Annotated

from fastapi import Depends
from src.city.repository import CityRepository
from src.database.deps import SessionDep
from src.species.repository import SpeciesRepository
from src.tackle.admin_service import TackleAdminService
from src.tackle.repository import TackleRepository
from src.tackle.service import TackleService


def get_tackle_service(session: SessionDep) -> TackleService:
    return TackleService(TackleRepository(session))


TackleServiceDep = Annotated[TackleService, Depends(get_tackle_service)]


def get_tackle_admin_service(session: SessionDep) -> TackleAdminService:
    return TackleAdminService(
        TackleRepository(session), CityRepository(session), SpeciesRepository(session)
    )


TackleAdminServiceDep = Annotated[TackleAdminService, Depends(get_tackle_admin_service)]
