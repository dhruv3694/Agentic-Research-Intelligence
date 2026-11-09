import logging
from typing import Any

import httpx
from pydantic import ValidationError

from backend.app.schemas.sources import SearchResult
from backend.app.services.search.base import (
    InvalidSearchResponseError,
    SearchProviderError,
    SearchTimeoutError,
    SearchUnavailableError,
)

logger = logging.getLogger(__name__)


class SearXNGSearchProvider:
    def __init__(self, client: httpx.AsyncClient, max_results: int) -> None:
        self._client = client
        self._max_results = max_results

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        bounded_limit = min(max(limit, 1), self._max_results)
        try:
            response = await self._client.get(
                "/search",
                params={"q": query, "format": "json", "safesearch": 1},
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("SearXNG request timed out (%s).", type(exc).__name__)
            raise SearchTimeoutError from exc
        except (httpx.ConnectError, httpx.RequestError) as exc:
            logger.warning("SearXNG request failed (%s).", type(exc).__name__)
            raise SearchUnavailableError from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("SearXNG returned HTTP %s.", exc.response.status_code)
            raise SearchProviderError from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise InvalidSearchResponseError from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise InvalidSearchResponseError

        results: list[SearchResult] = []
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            truncated_fields: list[str] = []
            title = item.get("title")
            snippet = item.get("content")
            if isinstance(title, str) and len(title) > 500:
                title = title[:500]
                truncated_fields.append("title")
            if isinstance(snippet, str) and len(snippet) > 4000:
                snippet = snippet[:4000]
                truncated_fields.append("snippet")
            metadata: dict[str, Any] = {}
            for key in ("engine", "engines", "score", "category"):
                if key not in item:
                    continue
                value = item[key]
                if isinstance(value, str):
                    if len(value) > 500:
                        value = value[:500]
                        truncated_fields.append(f"metadata.{key}")
                    metadata[key] = value
                elif isinstance(value, list):
                    strings = [entry for entry in value if isinstance(entry, str)]
                    bounded = [entry[:150] for entry in strings[:10]]
                    if len(strings) != len(value) or bounded != value:
                        truncated_fields.append(f"metadata.{key}")
                    metadata[key] = bounded
                elif value is None or isinstance(value, int | float | bool):
                    metadata[key] = value
                else:
                    truncated_fields.append(f"metadata.{key}")
            if truncated_fields:
                metadata["truncated_fields"] = truncated_fields
            raw_result: dict[str, Any] = {
                "title": title,
                "url": item.get("url"),
                "snippet": snippet,
                "source_type": "web",
                "publication_date": item.get("publishedDate"),
                "metadata": metadata,
            }
            try:
                results.append(SearchResult.model_validate(raw_result))
            except ValidationError:
                logger.warning("Skipping malformed SearXNG result.")
        return results[:bounded_limit]
