"""Persistent driver preference storage using Mem0."""

from __future__ import annotations

import os
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

_fallback_memory: dict[str, list[str]] = {}


class DriverMemory:
    """Driver memory via Mem0 with local fallback."""

    def __init__(self) -> None:
        self._memory = None
        try:
            from mem0 import Memory

            config: dict[str, Any] = {
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                        "api_key": os.getenv("OPENAI_API_KEY", ""),
                    },
                },
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "host": os.getenv("QDRANT_HOST", "qdrant"),
                        "port": int(os.getenv("QDRANT_PORT", "6333")),
                        "collection_name": "driver_memories",
                    },
                },
            }
            api_base = os.getenv("LLM_API_BASE")
            if api_base:
                config["llm"]["config"]["openai_base_url"] = api_base

            self._memory = Memory.from_config(config)
        except Exception as exc:
            logger.warning("mem0_init_failed_using_fallback", error=str(exc))

    def _format_preferences(self, memories: Any) -> dict:
        items = []
        if isinstance(memories, dict) and "results" in memories:
            items = memories["results"]
        elif isinstance(memories, list):
            items = memories
        prefs = [m.get("memory", m.get("text", str(m))) for m in items if m]
        return {
            "preferences": prefs,
            "summary": "; ".join(prefs[:5]) if prefs else "No stored preferences yet.",
        }

    async def get_preferences(self, driver_id: str) -> dict:
        if self._memory:
            try:
                memories = self._memory.search(
                    query="driver preferences equipment lanes deadhead",
                    user_id=driver_id,
                    limit=10,
                )
                return self._format_preferences(memories)
            except Exception as exc:
                logger.warning("mem0_search_failed", error=str(exc))

        stored = _fallback_memory.get(driver_id, [])
        return {"preferences": stored, "summary": "; ".join(stored) if stored else "No stored preferences yet."}

    async def save_interaction(self, driver_id: str, interaction_summary: str) -> None:
        if self._memory:
            try:
                self._memory.add(interaction_summary, user_id=driver_id)
                return
            except Exception as exc:
                logger.warning("mem0_add_failed", error=str(exc))
        _fallback_memory.setdefault(driver_id, []).append(interaction_summary)

    async def save_preference(self, driver_id: str, preference: str) -> None:
        await self.save_interaction(driver_id, f"Preference: {preference}")
