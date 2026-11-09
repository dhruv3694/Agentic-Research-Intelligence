import asyncio

import httpx
import pytest

from backend.app.services.search.base import (
    InvalidSearchResponseError,
    SearchProviderError,
    SearchTimeoutError,
    SearchUnavailableError,
)
from backend.app.services.search.providers.searxng import SearXNGSearchProvider


def search_with(handler: httpx.MockTransport):
    async def execute():
        async with httpx.AsyncClient(
            base_url="http://searxng.test",
            transport=handler,
            timeout=1,
        ) as client:
            return await SearXNGSearchProvider(client, max_results=2).search("test query", 10)

    return asyncio.run(execute())


def test_searxng_search_normalizes_result_and_limits_results():
    requests = []

    def responder(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Title",
                        "url": "https://example.org/article",
                        "content": "Snippet",
                        "engine": "example",
                    },
                    {"url": "https://example.org/second"},
                    {"title": "invalid", "url": "javascript:alert(1)"},
                ],
            },
        )

    results = search_with(httpx.MockTransport(responder))

    assert len(results) == 2
    assert results[0].title == "Title"
    assert results[0].snippet == "Snippet"
    assert results[0].publication_date is None
    assert results[0].metadata["engine"] == "example"
    assert requests[0].url.params["format"] == "json"


@pytest.mark.parametrize("payload", [{}, {"results": "not a list"}])
def test_searxng_rejects_malformed_response(payload):
    handler = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))

    with pytest.raises(InvalidSearchResponseError):
        search_with(handler)


def test_searxng_reports_timeout():
    def responder(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(SearchTimeoutError):
        search_with(httpx.MockTransport(responder))


def test_searxng_reports_connection_failure():
    def responder(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(SearchUnavailableError):
        search_with(httpx.MockTransport(responder))


def test_searxng_reports_upstream_http_error():
    handler = httpx.MockTransport(lambda _: httpx.Response(403))

    with pytest.raises(SearchProviderError):
        search_with(handler)
