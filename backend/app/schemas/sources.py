import json
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
    source_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=500)
    url: str = Field(max_length=2048)
    description: str | None = Field(default=None, max_length=4000)
    source_type: str = Field(default="web", max_length=64)
    publication_date: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    original_query: str = Field(max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=20)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_source_url(value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_metadata(value)
        return value

    @field_validator("publication_date", "retrieved_at")
    @classmethod
    def require_timezone_if_present(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class SearchResult(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    url: str = Field(max_length=2048)
    snippet: str | None = Field(default=None, max_length=4000)
    source_type: str = Field(default="web", max_length=64)
    publication_date: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=20)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return validate_source_url(value)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_metadata(value)
        return value

    @field_validator("publication_date")
    @classmethod
    def require_timezone_if_present(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def _validate_metadata(metadata: dict[str, Any]) -> None:
    for key, value in metadata.items():
        if not key or len(key) > 100:
            raise ValueError("metadata keys must contain 1 to 100 characters")
        if isinstance(value, str):
            if len(value) > 500:
                raise ValueError("metadata strings must not exceed 500 characters")
        elif isinstance(value, list):
            if len(value) > 20 or any(
                not isinstance(item, str) or len(item) > 200 for item in value
            ):
                raise ValueError("metadata lists must contain at most 20 short strings")
        elif value is not None and (
            isinstance(value, dict) or not isinstance(value, int | float | bool)
        ):
            raise ValueError("metadata values must be scalar or a list of strings")

    try:
        encoded = json.dumps(metadata, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata must contain JSON-compatible values") from exc
    if len(encoded.encode("utf-8")) > 4096:
        raise ValueError("metadata must not exceed 4096 bytes")
