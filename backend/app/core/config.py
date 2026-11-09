from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agentic Research Intelligence"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        normalized = value.lower()
        allowed = {"development", "production", "test"}
        if normalized not in allowed:
            raise ValueError("app_env must be one of: development, production, test")
        return normalized

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        return value.upper()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
