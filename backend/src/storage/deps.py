from functools import lru_cache

from src.storage.client import StorageClient
from src.storage.settings import storage_settings


@lru_cache
def get_storage_client() -> StorageClient:
    return StorageClient(storage_settings)
