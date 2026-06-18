"""DeadMile AI — API Gateway"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.config import settings
from app.db import close_pool
from app.middleware.cors import setup_cors
from app.routers.loads import router as loads_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await close_pool()


app = FastAPI(
    title="DeadMile AI — API Gateway",
    description="Main REST API for load optimization and recommendations",
    version="0.2.0",
    lifespan=lifespan,
)

setup_cors(app)
app.include_router(loads_router)
app.mount("/metrics", make_asgi_app())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "DeadMile AI API Gateway",
        "docs": "/docs",
        "health": "/health",
    }
