"""Optional API key authentication for production deployments."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

PUBLIC_PATHS = {
    "/",
    "/health",
    "/health/all",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key when API_GATEWAY_KEY is configured."""

    async def dispatch(self, request: Request, call_next: Callable):
        if not settings.require_api_key:
            carrier_id = request.headers.get("X-Carrier-Id") or request.headers.get("x-carrier-id") or "default"
            request.state.carrier_id = carrier_id[:64]
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"
        if path in PUBLIC_PATHS or path.startswith("/health"):
            return await call_next(request)

        provided = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        if not provided:
            return JSONResponse(status_code=401, content={"detail": "Missing X-API-Key header"})

        if not hmac.compare_digest(provided, settings.api_gateway_key):
            return JSONResponse(status_code=403, content={"detail": "Invalid API key"})

        request.state.carrier_id = settings.default_carrier_id
        return await call_next(request)
