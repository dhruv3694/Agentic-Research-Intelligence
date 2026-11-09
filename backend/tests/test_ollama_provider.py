import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest

from backend.app.services.llm.base import (
    EmptyGenerationError,
    InvalidProviderResponseError,
    ModelNotFoundError,
    ProviderTimeoutError,
    RuntimeUnavailableError,
    UpstreamError,
)
from backend.app.services.llm.ollama_provider import OllamaProvider

OLLAMA_MODEL = "qwen3:4b"
MODEL = {"name": OLLAMA_MODEL, "model": OLLAMA_MODEL}


def run_with_provider(
    handler: httpx.MockTransport,
    operation: Callable[[OllamaProvider], Awaitable[object]],
) -> object:
    async def execute() -> object:
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=handler,
            timeout=1,
        ) as client:
            provider = OllamaProvider(client, OLLAMA_MODEL, 0.2, 4096)
            return await operation(provider)

    return asyncio.run(execute())


def test_connection_check_succeeds():
    handler = httpx.MockTransport(lambda _: httpx.Response(200, json={"models": [MODEL]}))

    result = run_with_provider(handler, lambda provider: provider.check_connection())

    assert result is True


def test_connection_check_fails_without_ollama():
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = run_with_provider(httpx.MockTransport(unavailable), lambda p: p.check_connection())

    assert result is False


def test_lists_models():
    handler = httpx.MockTransport(lambda _: httpx.Response(200, json={"models": [MODEL]}))

    result = run_with_provider(handler, lambda provider: provider.list_models())

    assert len(result) == 1
    assert result[0].name == OLLAMA_MODEL


def test_missing_model_is_reported():
    handler = httpx.MockTransport(lambda _: httpx.Response(200, json={"models": []}))

    with pytest.raises(ModelNotFoundError):
        run_with_provider(
            handler,
            lambda provider: provider.generate("prompt", None, 100),
        )


def test_generates_text_and_maps_options():
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [MODEL]})
        return httpx.Response(
            200,
            json={"response": "answer", "done": True, "total_duration": 1000},
        )

    result = run_with_provider(
        httpx.MockTransport(responder), lambda p: p.generate("prompt", 0.5, 37)
    )

    assert result[:2] == ("answer", True)
    assert result[2] >= 0
    import json

    payload = json.loads(requests[1].content)
    assert payload["options"] == {
        "temperature": 0.5,
        "num_ctx": 4096,
        "num_predict": 37,
    }


def test_generation_timeout_is_reported():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [MODEL]})
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(ProviderTimeoutError):
        run_with_provider(
            httpx.MockTransport(responder),
            lambda provider: provider.generate("prompt", None, 100),
        )


@pytest.mark.parametrize(
    "payload",
    [{}, {"models": [{"name": "bad-model"}]}],
)
def test_malformed_model_inventory_is_rejected(payload):
    handler = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))

    with pytest.raises(InvalidProviderResponseError):
        run_with_provider(handler, lambda provider: provider.list_models())


def test_malformed_generation_response_is_rejected():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [MODEL]})
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(InvalidProviderResponseError):
        run_with_provider(
            httpx.MockTransport(responder),
            lambda provider: provider.generate("prompt", None, 100),
        )


def test_empty_generation_is_rejected():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [MODEL]})
        return httpx.Response(200, json={"response": " ", "done": True})

    with pytest.raises(EmptyGenerationError):
        run_with_provider(
            httpx.MockTransport(responder),
            lambda provider: provider.generate("prompt", None, 100),
        )


def test_unexpected_upstream_status_is_reported():
    handler = httpx.MockTransport(lambda _: httpx.Response(500, json={"error": "failure"}))

    with pytest.raises(UpstreamError):
        run_with_provider(handler, lambda provider: provider.list_models())


def test_runtime_connection_error_is_reported():
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(RuntimeUnavailableError):
        run_with_provider(
            httpx.MockTransport(unavailable),
            lambda provider: provider.list_models(),
        )
