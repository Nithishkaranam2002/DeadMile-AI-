"""Agent tools package."""

from app.tools.calculate_profitability import calculate_profitability
from app.tools.driver_preferences import get_driver_preferences
from app.tools.fuel_prices import get_fuel_prices
from app.tools.load_chain import find_load_chain
from app.tools.market_score import get_market_score
from app.tools.rate_predictor import predict_lane_rate
from app.tools.search_loads import search_loads
from app.tools.semantic_search import semantic_load_search

ALL_TOOLS = [
    search_loads,
    calculate_profitability,
    get_market_score,
    predict_lane_rate,
    find_load_chain,
    get_fuel_prices,
    semantic_load_search,
    get_driver_preferences,
]

__all__ = ["ALL_TOOLS"]
