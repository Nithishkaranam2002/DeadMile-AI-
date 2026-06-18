"""LangGraph ReAct agent definition."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Optional

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.prompts import SYSTEM_PROMPT
from app.tools import ALL_TOOLS

logger = structlog.get_logger(__name__)


def _build_llm() -> ChatOpenAI:
    api_key = os.getenv("FEATHERLESS_API_KEY") or os.getenv("OPENAI_API_KEY", "sk-placeholder")
    base_url = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
    model = os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-70B-Instruct")
    if not model.startswith("openai/") and base_url:
        model = model.replace("openai/", "")

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    if os.getenv("FEATHERLESS_API_KEY"):
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


@lru_cache
def get_checkpointer() -> MemorySaver:
    return MemorySaver()


@lru_cache
def get_agent_graph():
    llm = _build_llm()
    return create_react_agent(llm, ALL_TOOLS, checkpointer=get_checkpointer())


def build_initial_state(
    message: str,
    driver_lat: Optional[float] = None,
    driver_lng: Optional[float] = None,
    equipment: Optional[str] = None,
    max_deadhead: int = 250,
    driver_id: Optional[str] = None,
    driver_preferences: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    context_parts = [SYSTEM_PROMPT, "\n\n--- Driver Context ---"]
    if driver_lat is not None and driver_lng is not None:
        context_parts.append(f"Location: ({driver_lat}, {driver_lng})")
    if equipment:
        context_parts.append(f"Equipment: {equipment}")
    context_parts.append(f"Max deadhead: {max_deadhead} miles")
    if driver_preferences and driver_preferences.get("summary"):
        context_parts.append(f"Driver preferences: {driver_preferences['summary']}")
    if driver_id:
        context_parts.append(f"Driver ID: {driver_id}")

    system = SystemMessage(content="\n".join(context_parts))
    human = HumanMessage(content=message)

    return {
        "messages": [system, human],
        "driver_lat": driver_lat,
        "driver_lng": driver_lng,
        "equipment": equipment,
        "max_deadhead": max_deadhead,
        "driver_id": driver_id,
        "driver_preferences": driver_preferences,
        "session_id": session_id,
        "recommended_loads": [],
        "load_chain": None,
        "market_scores": [],
        "rate_predictions": [],
        "current_step": "analyzing",
        "thinking_steps": [],
        "final_response": None,
    }


async def extract_final_response(result: dict) -> str:
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            if not getattr(msg, "tool_calls", None):
                return msg.content
        if getattr(msg, "content", None) and type(msg).__name__ == "AIMessage":
            if not getattr(msg, "tool_calls", None):
                return msg.content
    return "I analyzed the available loads but couldn't generate a final response. Please try again."
