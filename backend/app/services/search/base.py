from typing import Protocol

from backend.app.schemas.sources import SearchResult


class SearchProviderError(Exception):
    """Base class for expected search provider failures."""

    code = "search_provider_error"
    status_code = 502
    public_message = "The search provider could not complete the request."


class SearchUnavailableError(SearchProviderError):
    code = "search_unavailable"
    status_code = 503
    public_message = "Search is unavailable. Configure and start a search provider."


class SearchTimeoutError(SearchProviderError):
    code = "search_timeout"
    status_code = 504
    public_message = "The search provider request timed out."


class InvalidSearchResponseError(SearchProviderError):
    code = "invalid_search_response"
    status_code = 502
    public_message = "The search provider returned an invalid response."


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int) -> list[SearchResult]: ...


class DisabledSearchProvider:
    async def search(self, query: str, limit: int) -> list[SearchResult]:
        raise SearchUnavailableError
