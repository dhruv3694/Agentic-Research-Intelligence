import json
from uuid import uuid4

from backend.app.schemas.sources import SearchResult
from backend.app.services.research.retrieval import ResearchRetrievalService
from backend.app.services.research.source_processor import SourceProcessor


def test_plan_endpoint_returns_llm_generated_plan(client, ollama):
    ollama.generate_payload["response"] = json.dumps(
        {
            "topic": "AI in finance",
            "sub_questions": [
                "What applications use AI in finance?",
                "What risks affect AI in finance?",
            ],
        }
    )

    response = client.post(
        "/api/v1/research/plan",
        json={"question": "How is AI changing finance?", "max_subquestions": 2},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["research_id"]
    assert result["status"] == "planned"
    assert result["plan"]["generated_by"] == "llm"
    assert len(result["plan"]["sub_questions"]) == 2


def test_backend_startup_does_not_require_ollama_or_search(client, ollama):
    assert ollama.requests == []
    assert client.get("/api/v1/health").status_code == 200


def test_plan_endpoint_falls_back_when_ollama_is_unavailable(client, ollama):
    ollama.connection_error = True

    response = client.post(
        "/api/v1/research/plan",
        json={"question": "How is AI changing finance?"},
    )

    assert response.status_code == 200
    assert response.json()["plan"]["generated_by"] == "deterministic_fallback"
    assert response.json()["plan"]["fallback_reason"] == "llm_unavailable"


def test_plan_endpoint_rejects_invalid_question(client):
    response = client.post("/api/v1/research/plan", json={"question": "AI"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_retrieve_endpoint_reports_unconfigured_search_provider(client):
    plan_response = client.post(
        "/api/v1/research/plan",
        json={"question": "How is AI changing finance?"},
    )
    plan_data = plan_response.json()
    response = client.post(
        "/api/v1/research/retrieve",
        json={
            "research_id": plan_data["research_id"],
            "question": plan_data["question"],
            "plan": plan_data["plan"],
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "search_unavailable"


def test_retrieve_endpoint_returns_normalized_sources(client):
    class FakeSearchProvider:
        async def search(self, query, limit):
            return [
                SearchResult(
                    title="Source title",
                    url="https://example.org/research",
                    snippet="A source snippet.",
                    metadata={"engine": "mock"},
                )
            ]

    client.app.state.research_retrieval_service = ResearchRetrievalService(
        FakeSearchProvider(),
        SourceProcessor(),
        max_results=3,
        max_concurrent_searches=2,
    )
    plan_data = client.post(
        "/api/v1/research/plan",
        json={"question": "How is AI changing finance?"},
    ).json()

    response = client.post(
        "/api/v1/research/retrieve",
        json={
            "research_id": plan_data["research_id"],
            "question": plan_data["question"],
            "plan": plan_data["plan"],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert len(result["sources"]) == 1
    assert result["sources"][0]["url"] == "https://example.org/research"
    assert (
        result["sources"][0]["original_query"] == plan_data["plan"]["sub_questions"][0]["question"]
    )
    assert result["sources"][0]["publication_date"] is None


def test_research_routes_are_documented_in_openapi(client):
    schema = client.get("/openapi.json").json()

    assert "/api/v1/research/plan" in schema["paths"]
    assert "/api/v1/research/retrieve" in schema["paths"]
    assert "/api/v1/research/run" in schema["paths"]


def test_run_endpoint_returns_inspectable_failed_workflow_when_search_is_disabled(client):
    response = client.post(
        "/api/v1/research/run",
        json={"question": "How is AI changing finance?"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed"
    assert result["plan"]["generated_by"] == "deterministic_fallback"
    assert result["errors"][0]["stage"] == "researcher"
    assert result["errors"][0]["code"] == "search_unavailable"
    assert any(
        item["agent_name"] == "planner" and item["status"] == "succeeded"
        for item in result["execution_history"]
    )


def test_retrieve_endpoint_rejects_invalid_plan_shape(client):
    response = client.post(
        "/api/v1/research/retrieve",
        json={
            "research_id": str(uuid4()),
            "question": "How is AI changing finance?",
            "plan": {
                "topic": "AI",
                "generated_by": "llm",
                "sub_questions": [],
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
