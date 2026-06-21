"""Environment-configurable cost settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared import constants as c


class CostSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    fuel_price_per_gallon: float = Field(default=c.FUEL_PRICE_PER_GALLON, alias="DEFAULT_FUEL_PRICE")
    avg_mpg_loaded: float = Field(default=c.AVG_MPG_LOADED, alias="DEFAULT_FUEL_MPG")
    avg_mpg_empty: float = c.AVG_MPG_EMPTY
    driver_cpm: float = Field(default=c.DRIVER_CPM, alias="DEFAULT_DRIVER_PAY_PER_MILE")
    insurance_per_mile: float = Field(default=c.INSURANCE_PER_MILE, alias="DEFAULT_INSURANCE_PER_MILE")
    maintenance_per_mile: float = Field(default=c.MAINTENANCE_PER_MILE, alias="DEFAULT_MAINTENANCE_PER_MILE")
    tolls_per_mile: float = Field(default=c.TOLLS_PER_MILE, alias="DEFAULT_TOLL_RATE_PER_MILE")
    dispatch_fee_percent: float = c.DISPATCH_FEE_PERCENT
    factoring_fee_percent: float = c.FACTORING_FEE_PERCENT
    overhead_per_mile: float = c.OVERHEAD_PER_MILE
    hazmat_premium: float = c.HAZMAT_PREMIUM
    team_driver_multiplier: float = c.TEAM_DRIVER_MULTIPLIER
    road_factor: float = c.ROAD_FACTOR


cost_settings = CostSettings()


def merge_cost_settings(overrides: dict | None) -> CostSettings:
    if not overrides:
        return cost_settings
    clean = {k: v for k, v in overrides.items() if v is not None}
    if not clean:
        return cost_settings
    return cost_settings.model_copy(update=clean)
