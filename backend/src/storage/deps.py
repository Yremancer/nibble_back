from typing import Annotated

from fastapi import Depends, Request
from src.database.deps import SessionDep
from src.storage.client import StorageClient
from src.storage.repository import FileRepository
from src.storage.service import FileService


def get_storage_client(request: Request) -> StorageClient:
    return request.app.state.storage


StorageClientDep = Annotated[StorageClient, Depends(get_storage_client)]


def get_file_repository(session: SessionDep) -> FileRepository:
    return FileRepository(session)


FileRepositoryDep = Annotated[FileRepository, Depends(get_file_repository)]


def get_file_service(repo: FileRepositoryDep, storage: StorageClientDep) -> FileService:
    return FileService(repo, storage)


FileServiceDep = Annotated[FileService, Depends(get_file_service)]
