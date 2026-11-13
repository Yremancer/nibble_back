from fastapi import APIRouter
from src.weather.router import router as weather_router

api_controller = APIRouter()
api_controller.include_router(weather_router)
