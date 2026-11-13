from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.api import api_controller
from src.exc_handler import register_exception_handlers
from src.settings import settings
from src.storage.setup import setup_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as http:
        app.state.http = http
        async with setup_storage(app):
            yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
app.include_router(api_controller)

register_exception_handlers(app)
