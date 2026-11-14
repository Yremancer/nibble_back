from typing import Annotated

from fastapi import Depends
from src.database.deps import SessionDep
from src.species.admin_service import SpeciesAdminService
from src.species.repository import SpeciesRepository
from src.species.service import SpeciesService
from src.storage.deps import ImageServiceDep


def get_species_service(session: SessionDep, images: ImageServiceDep) -> SpeciesService:
    return SpeciesService(SpeciesRepository(session), images)


SpeciesServiceDep = Annotated[SpeciesService, Depends(get_species_service)]


def get_species_admin_service(
    session: SessionDep, images: ImageServiceDep
) -> SpeciesAdminService:
    return SpeciesAdminService(SpeciesRepository(session), images)


SpeciesAdminServiceDep = Annotated[
    SpeciesAdminService, Depends(get_species_admin_service)
]
