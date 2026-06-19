"""Unified LLM interface via LiteLLM (OpenAI primary, optional alt providers)."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import structlog
from litellm import acompletion

logger = structlog.get_logger(__name__)


class LLMClient:
    """Unified LLM interface with automatic fallback."""

    def __init__(self) -> None:
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY", "")
        self.api_base = os.getenv("LLM_API_BASE") or None
        self.fallback_model = os.getenv("FALLBACK_LLM_MODEL", "gpt-4o-mini")
        self.fallback_api_key = os.getenv("OPENAI_API_KEY", "")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.1,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096,
            "api_key": self.api_key,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            return await acompletion(**kwargs)
        except Exception as exc:
            logger.warning("primary_llm_failed", error=str(exc), model=self.model)
            if self.fallback_api_key and self.model != self.fallback_model:
                fallback_kwargs: dict[str, Any] = {
                    "model": self.fallback_model,
                    "messages": messages,
                    "api_key": self.fallback_api_key,
                    "temperature": temperature,
                    "max_tokens": 4096,
                }
                if tools:
                    fallback_kwargs["tools"] = tools
                    fallback_kwargs["tool_choice"] = "auto"
                return await acompletion(**fallback_kwargs)
            raise

    @staticmethod
    def message_content(response: Any) -> str:
        choice = response.choices[0]
        msg = choice.message
        if hasattr(msg, "content") and msg.content:
            return msg.content
        if isinstance(msg, dict):
            return msg.get("content", "") or ""
        return ""

    @staticmethod
    def tool_calls(response: Any) -> list[dict]:
        choice = response.choices[0]
        msg = choice.message
        calls = getattr(msg, "tool_calls", None) or (msg.get("tool_calls") if isinstance(msg, dict) else None)
        if not calls:
            return []
        result = []
        for tc in calls:
            fn = tc.function if hasattr(tc, "function") else tc.get("function", {})
            result.append({
                "id": tc.id if hasattr(tc, "id") else tc.get("id"),
                "name": fn.name if hasattr(fn, "name") else fn.get("name"),
                "arguments": fn.arguments if hasattr(fn, "arguments") else fn.get("arguments", "{}"),
            })
        return result

    @staticmethod
    def to_openai_messages(lc_messages: list) -> list[dict]:
        """Convert LangChain messages to OpenAI format."""
        out = []
        for m in lc_messages:
            role = getattr(m, "type", "user")
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            elif role == "system":
                role = "system"
            elif role == "tool":
                out.append({
                    "role": "tool",
                    "content": m.content,
                    "tool_call_id": getattr(m, "tool_call_id", ""),
                })
                continue
            entry: dict[str, Any] = {"role": role, "content": m.content}
            if hasattr(m, "tool_calls") and m.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.get("id"),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]) if isinstance(tc.get("args"), dict) else tc.get("args", "{}"),
                        },
                    }
                    for tc in m.tool_calls
                ]
            out.append(entry)
        return out
