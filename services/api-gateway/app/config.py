from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "api-gateway"
    service_port: int = 8000
    database_url: str = "postgresql+asyncpg://deadmile:deadmile@postgres:5432/deadmile"
    redis_url: str = "redis://redis:6379/0"
    agent_core_url: str = "http://agent-core:8001"
    profitability_engine_url: str = "http://profitability-engine:8004"
    market_intelligence_url: str = "http://market-intelligence:8005"
    cors_origins: list[str] = ["http://localhost:3000", "http://frontend:3000"]


settings = Settings()
