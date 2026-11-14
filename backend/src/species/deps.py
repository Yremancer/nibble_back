from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.species.admin_service import SpeciesAdminService
from src.species.repository import SpeciesRepository
from src.species.service import SpeciesService


def get_species_service(session: SessionDep) -> SpeciesService:
    return SpeciesService(SpeciesRepository(session))


SpeciesServiceDep = Annotated[SpeciesService, Depends(get_species_service)]


def get_species_admin_service(session: SessionDep) -> SpeciesAdminService:
    return SpeciesAdminService(SpeciesRepository(session))


SpeciesAdminServiceDep = Annotated[
    SpeciesAdminService, Depends(get_species_admin_service)
]
