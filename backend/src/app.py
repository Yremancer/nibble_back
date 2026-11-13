import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.api import api_controller
from src.settings import settings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0))
app.include_router(api_controller)
