import os
from collections.abc import Iterator

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "INFO")

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.core.config import settings


class MockOllama:
    def __init__(self) -> None:
        self.models: list[dict[str, object]] = [
            {
                "name": "qwen3:4b",
                "model": "qwen3:4b",
                "size": 2_500_000_000,
                "details": {
                    "family": "qwen3",
                    "parameter_size": "4.0B",
                    "quantization_level": "Q4_K_M",
                },
            }
        ]
        self.generate_payload: dict[str, object] = {
            "model": "qwen3:4b",
            "response": "A generated answer.",
            "done": True,
            "total_duration": 1_000_000,
        }
        self.tags_status = 200
        self.generate_status = 200
        self.connection_error = False
        self.generation_timeout = False
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.connection_error:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(self.tags_status, json={"models": self.models})
        if request.url.path == "/api/generate":
            if self.generation_timeout:
                raise httpx.ReadTimeout("upstream timeout", request=request)
            return httpx.Response(self.generate_status, json=self.generate_payload)
        return httpx.Response(404, json={"error": "not found"})


@pytest.fixture()
def ollama() -> MockOllama:
    return MockOllama()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, ollama: MockOllama) -> Iterator[TestClient]:
    monkeypatch.setattr(
        main,
        "create_ollama_http_client",
        lambda: httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.ollama_timeout),
            transport=httpx.MockTransport(ollama),
        ),
    )
    with TestClient(main.app) as test_client:
        yield test_client
