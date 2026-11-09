import json


def test_status_endpoint_reports_configured_model(client):
    response = client.get("/api/v1/llm/status")

    assert response.status_code == 200
    assert response.json() == {
        "runtime_status": "available",
        "connection_available": True,
        "configured_model": "qwen3:4b",
        "model_installed": True,
        "message": "Configured model is ready.",
    }


def test_status_endpoint_reports_missing_model(client, ollama):
    ollama.models = []

    response = client.get("/api/v1/llm/status")

    assert response.status_code == 200
    assert response.json()["connection_available"] is True
    assert response.json()["model_installed"] is False


def test_status_endpoint_reports_unavailable_runtime(client, ollama):
    ollama.connection_error = True

    response = client.get("/api/v1/llm/status")

    assert response.status_code == 200
    assert response.json()["runtime_status"] == "unavailable"
    assert response.json()["connection_available"] is False
    assert response.json()["model_installed"] is None


def test_models_endpoint_returns_installed_models(client):
    response = client.get("/api/v1/llm/models")

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "qwen3:4b"
    assert response.json()["models"][0]["details"]["parameter_size"] == "4.0B"


def test_models_endpoint_handles_runtime_failure(client, ollama):
    ollama.connection_error = True

    response = client.get("/api/v1/llm/models")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "runtime_unavailable"
    assert "connection refused" not in response.text


def test_generate_endpoint_returns_measured_response(client, ollama):
    response = client.post(
        "/api/v1/llm/generate",
        json={
            "prompt": "Explain transformer attention.",
            "temperature": 0.4,
            "max_tokens": 64,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "qwen3:4b"
    assert payload["response"] == "A generated answer."
    assert payload["done"] is True
    assert payload["generation_time_ms"] >= 0

    generation_request = next(
        request for request in ollama.requests if request.url.path == "/api/generate"
    )
    request_payload = json.loads(generation_request.content)
    assert request_payload["options"]["num_predict"] == 64
    assert request_payload["options"]["temperature"] == 0.4
    assert request_payload["stream"] is False


def test_generate_endpoint_uses_defaults(client, ollama):
    response = client.post("/api/v1/llm/generate", json={"prompt": "Hello"})

    assert response.status_code == 200
    request = next(request for request in ollama.requests if request.url.path == "/api/generate")
    payload = json.loads(request.content)
    assert payload["options"]["temperature"] == 0.2
    assert payload["options"]["num_predict"] == 512
    assert payload["options"]["num_ctx"] == 4096


def test_generate_rejects_invalid_temperature(client):
    response = client.post(
        "/api/v1/llm/generate",
        json={"prompt": "Hello", "temperature": 2.1},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_generate_rejects_invalid_max_tokens(client):
    response = client.post(
        "/api/v1/llm/generate",
        json={"prompt": "Hello", "max_tokens": 8193},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_generate_rejects_empty_prompt(client):
    response = client.post("/api/v1/llm/generate", json={"prompt": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_generate_rejects_blank_prompt(client):
    response = client.post("/api/v1/llm/generate", json={"prompt": "  "})

    assert response.status_code == 422


def test_generate_rejects_oversized_prompt(client):
    response = client.post(
        "/api/v1/llm/generate",
        json={"prompt": "a" * 20_001},
    )

    assert response.status_code == 422


def test_generate_reports_missing_model(client, ollama):
    ollama.models = []

    response = client.post("/api/v1/llm/generate", json={"prompt": "Hello"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_generate_reports_runtime_unavailable(client, ollama):
    ollama.connection_error = True

    response = client.post("/api/v1/llm/generate", json={"prompt": "Hello"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "runtime_unavailable"


def test_generate_rejects_empty_upstream_response(client, ollama):
    ollama.generate_payload["response"] = "  "

    response = client.post("/api/v1/llm/generate", json={"prompt": "Hello"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "empty_generation"


def test_generate_rejects_malformed_upstream_response(client, ollama):
    ollama.generate_payload = {"not_response": True}

    response = client.post("/api/v1/llm/generate", json={"prompt": "Hello"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_provider_response"


def test_models_endpoint_handles_unexpected_upstream_status(client, ollama):
    ollama.tags_status = 500

    response = client.get("/api/v1/llm/models")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


def test_generation_request_is_not_logged_or_returned_on_validation_error(client):
    secret_prompt = "private-user-prompt"
    response = client.post(
        "/api/v1/llm/generate",
        json={"prompt": secret_prompt, "temperature": 9},
    )

    assert response.status_code == 422
    assert secret_prompt not in response.text


def test_generation_http_timeout_maps_to_gateway_timeout(client, ollama):
    ollama.generation_timeout = True
    response = client.post("/api/v1/llm/generate", json={"prompt": "Hello"})

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "provider_timeout"
