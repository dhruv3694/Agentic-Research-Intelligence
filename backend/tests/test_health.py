import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings, settings


def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == settings.app_name
    assert payload["version"] == settings.app_version
    assert payload["status"] == "running"


def test_health_endpoint(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["application"]["name"] == settings.app_name
    assert payload["application"]["version"] == settings.app_version
    assert payload["application"]["environment"] == settings.app_env
    assert payload["message"] == "Service is healthy."


def test_openapi_schema_available(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == settings.app_name
    assert schema["info"]["version"] == settings.app_version
    generate_operation = schema["paths"]["/api/v1/llm/generate"]["post"]
    assert generate_operation["requestBody"]["content"]["application/json"]
    assert "200" in generate_operation["responses"]
    assert "422" in generate_operation["responses"]
    assert "504" in generate_operation["responses"]
    assert (
        schema["components"]["schemas"]["GenerateRequest"]["properties"]["prompt"]["maxLength"]
        == 20_000
    )


def test_docs_endpoint_available(client):
    response = client.get("/docs")

    assert response.status_code == 200


def test_configuration_defaults():
    assert settings.app_name == "Agentic Research Intelligence"
    assert settings.app_version == "0.1.0"
    assert settings.app_env in {"development", "test", "production"}
    assert settings.ollama_model == "qwen3:4b"
    assert settings.ollama_timeout > 0


@pytest.mark.parametrize(
    "values",
    [
        {"ollama_timeout": 0},
        {"ollama_temperature": 2.1},
        {"ollama_num_ctx": 0},
        {"ollama_base_url": "http://user:password@localhost:11434"},
        {"ollama_model": "  "},
        {"search_provider": "proprietary"},
        {"searxng_base_url": "file:///tmp/search"},
        {"searxng_base_url": "https://example.org/search-path"},
        {"search_timeout": 0},
        {"search_max_results": 21},
        {"research_max_subquestions": 0},
        {"research_max_concurrent_searches": 11},
    ],
)
def test_invalid_ollama_configuration_is_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
