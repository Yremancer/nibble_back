from fastapi import APIRouter
from src.aggregator.router import router as aggregator_router
from src.auth.router import router as auth_router
from src.city.router import router as city_router
from src.depth.router import router as depth_router
from src.post.router import router as post_router
from src.species.router import router as species_router
from src.spot.router import router as spot_router
from src.storage.router import router as storage_router
from src.weather.router import router as weather_router

api_controller = APIRouter()
api_controller.include_router(aggregator_router)
api_controller.include_router(auth_router)
api_controller.include_router(city_router)
api_controller.include_router(depth_router)
api_controller.include_router(post_router)
api_controller.include_router(species_router)
api_controller.include_router(spot_router)
api_controller.include_router(storage_router)
api_controller.include_router(weather_router)
