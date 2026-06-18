"""HTTP clients for internal microservice calls."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway:8000")
PROFITABILITY_ENGINE_URL = os.getenv("PROFITABILITY_ENGINE_URL", "http://profitability-engine:8004")
MARKET_INTELLIGENCE_URL = os.getenv("MARKET_INTELLIGENCE_URL", "http://market-intelligence:8005")

TIMEOUT = httpx.Timeout(30.0)


async def get_json(url: str, params: Optional[dict] = None) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def post_json(url: str, body: dict) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()
