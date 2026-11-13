from fastapi import APIRouter
from src.storage.router import router as storage_router

api_controller = APIRouter()
api_controller.include_router(storage_router)
