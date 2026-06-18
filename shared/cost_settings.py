"""Environment-configurable cost settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared import constants as c


class CostSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fuel_price_per_gallon: float = c.FUEL_PRICE_PER_GALLON
    avg_mpg_loaded: float = c.AVG_MPG_LOADED
    avg_mpg_empty: float = c.AVG_MPG_EMPTY
    driver_cpm: float = c.DRIVER_CPM
    insurance_per_mile: float = c.INSURANCE_PER_MILE
    maintenance_per_mile: float = c.MAINTENANCE_PER_MILE
    tolls_per_mile: float = c.TOLLS_PER_MILE
    dispatch_fee_percent: float = c.DISPATCH_FEE_PERCENT
    factoring_fee_percent: float = c.FACTORING_FEE_PERCENT
    overhead_per_mile: float = c.OVERHEAD_PER_MILE
    hazmat_premium: float = c.HAZMAT_PREMIUM
    team_driver_multiplier: float = c.TEAM_DRIVER_MULTIPLIER
    road_factor: float = c.ROAD_FACTOR


cost_settings = CostSettings()
