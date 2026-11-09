from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


def validate_source_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        not normalized
        or any(ord(character) < 32 for character in normalized)
        or parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("source URL must be a valid HTTP(S) URL without credentials")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("source URL contains an invalid port") from exc
    return normalized


class ResearchSource(BaseModel):
    source_id: str = Field(min_length=1)
    title: str | None = None
    url: str
    description: str | None = None
    source_type: str = "web"
    publication_date: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    original_query: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_source_url(value)

    @field_validator("publication_date", "retrieved_at")
    @classmethod
    def require_timezone_if_present(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class SearchResult(BaseModel):
    title: str | None = None
    url: str
    snippet: str | None = None
    source_type: str = "web"
    publication_date: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_source_url(value)

    @field_validator("publication_date")
    @classmethod
    def require_timezone_if_present(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
