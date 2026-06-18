"""Agent streaming context for SSE events during tool execution."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.streaming import AgentStreamManager

_stream_manager: ContextVar[Optional["AgentStreamManager"]] = ContextVar("stream_manager", default=None)
_session_id: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


def set_stream_context(manager: "AgentStreamManager", session_id: str) -> None:
    _stream_manager.set(manager)
    _session_id.set(session_id)


def clear_stream_context() -> None:
    _stream_manager.set(None)
    _session_id.set(None)


async def emit(event_type: str, data: dict) -> None:
    manager = _stream_manager.get()
    session_id = _session_id.get()
    if manager and session_id:
        await manager.emit(session_id, event_type, data)
