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
            metadata = {
                key: item[key] for key in ("engine", "engines", "score", "category") if key in item
            }
            raw_result: dict[str, Any] = {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("content"),
                "source_type": "web",
                "publication_date": item.get("publishedDate"),
                "metadata": metadata,
            }
            try:
                results.append(SearchResult.model_validate(raw_result))
            except ValidationError:
                logger.warning("Skipping malformed SearXNG result.")
        return results[:bounded_limit]
