from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Agentic Research Intelligence"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout: float = Field(default=120.0, gt=0, le=600)
    ollama_temperature: float = Field(default=0.2, ge=0, le=2)
    ollama_num_ctx: int = Field(default=4096, ge=1, le=32768)
    search_provider: str = "disabled"
    searxng_base_url: str = "http://localhost:8080"
    search_timeout: float = Field(default=15.0, gt=0, le=120)
    search_max_results: int = Field(default=5, ge=1, le=20)
    research_max_subquestions: int = Field(default=5, ge=1, le=10)
    research_max_concurrent_searches: int = Field(default=3, ge=1, le=10)
    research_workflow_timeout: float = Field(default=300.0, gt=0, le=600)

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
        normalized = value.upper()
        if normalized not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("log_level must be a valid Python logging level")
        return normalized

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("ollama_base_url must be an HTTP(S) URL without credentials")
        return normalized

    @field_validator("ollama_model")
    @classmethod
    def validate_ollama_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ollama_model must not be empty")
        return normalized

    @field_validator("search_provider")
    @classmethod
    def validate_search_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"disabled", "searxng"}:
            raise ValueError("search_provider must be one of: disabled, searxng")
        return normalized

    @field_validator("searxng_base_url")
    @classmethod
    def validate_searxng_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "searxng_base_url must be an HTTP(S) origin without credentials or a path"
            )
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
