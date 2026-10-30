"""Lab API. Module 0 exposes only a health endpoint."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="DeadMile AI Lab API", version="0.1.0")


class Health(BaseModel):
    status: Literal["ok"]
    service: str


@app.get("/health")
async def health() -> Health:
    return Health(status="ok", service="lab-api")
