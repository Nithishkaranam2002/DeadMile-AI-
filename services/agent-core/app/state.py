"""LangGraph agent state schema."""

from __future__ import annotations

from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    driver_lat: Optional[float]
    driver_lng: Optional[float]
    driver_city: Optional[str]
    driver_state: Optional[str]
    equipment: Optional[str]
    max_deadhead: int
    recommended_loads: list
    load_chain: Optional[dict]
    market_scores: list
    rate_predictions: list
    current_step: str
    thinking_steps: list
    final_response: Optional[str]
    driver_id: Optional[str]
    driver_preferences: Optional[dict]
    session_id: Optional[str]
