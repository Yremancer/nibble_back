from fastapi import APIRouter
from src.auth.router import router as auth_router
from src.storage.router import router as storage_router
from src.weather.router import router as weather_router

api_controller = APIRouter()
api_controller.include_router(auth_router)
api_controller.include_router(storage_router)
api_controller.include_router(weather_router)
