from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "deadmile"
    postgres_user: str = "deadmile"
    postgres_password: str = "deadmile_secret_change_me"
    database_url: str = "postgresql://deadmile:deadmile_secret_change_me@postgres:5432/deadmile"

    redis_url: str = "redis://redis:6379/0"

    kafka_bootstrap_servers: str = "kafka:29092"
    kafka_topic_loads: str = "raw-loads"
    kafka_group_load_processor: str = "load-processor-group"

    data_text_path: str = "/data/text"
    data_pdf_path: str = "/data/pdf"

    market_intelligence_url: str = "http://market-intelligence:8005"
    profitability_engine_url: str = "http://profitability-engine:8004"
    api_gateway_url: str = "http://api-gateway:8000"
    agent_core_url: str = "http://agent-core:8001"

    api_gateway_key: str = ""
    default_carrier_id: str = "default"

    @property
    def asyncpg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")

    @property
    def require_api_key(self) -> bool:
        return bool(self.api_gateway_key.strip())


settings = Settings()
