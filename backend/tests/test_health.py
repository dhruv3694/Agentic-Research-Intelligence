from backend.app.core.config import settings


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


def test_docs_endpoint_available(client):
    response = client.get("/docs")

    assert response.status_code == 200


def test_configuration_defaults():
    assert settings.app_name == "Agentic Research Intelligence"
    assert settings.app_version == "0.1.0"
    assert settings.app_env in {"development", "test", "production"}
