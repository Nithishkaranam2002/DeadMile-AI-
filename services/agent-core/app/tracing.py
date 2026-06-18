"""Langfuse tracing for agent runs."""

from __future__ import annotations

import os
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class AgentTracer:
    """Langfuse tracing wrapper with graceful degradation."""

    def __init__(self) -> None:
        self._langfuse = None
        self._enabled = False
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        if public_key and secret_key:
            try:
                from langfuse import Langfuse

                self._langfuse = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )
                self._enabled = True
            except Exception as exc:
                logger.warning("langfuse_init_failed", error=str(exc))

    def get_callback_handler(self, session_id: str, user_id: Optional[str] = None):
        if not self._enabled:
            return None
        try:
            from langfuse.callback import CallbackHandler

            return CallbackHandler(
                session_id=session_id,
                user_id=user_id,
                trace_name="deadmile-agent",
                tags=["production", "agent-core"],
            )
        except Exception as exc:
            logger.warning("langfuse_handler_failed", error=str(exc))
            return None

    def trace_tool_call(
        self,
        tool_name: str,
        input_data: dict,
        output_data: dict,
        duration_ms: float,
    ) -> None:
        if not self._langfuse:
            return
        try:
            self._langfuse.trace(
                name=f"tool:{tool_name}",
                input=input_data,
                output=output_data,
                metadata={"duration_ms": duration_ms},
            )
        except Exception as exc:
            logger.debug("langfuse_trace_failed", error=str(exc))
