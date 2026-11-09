import asyncio
from uuid import uuid4

import pytest

from backend.app.schemas.research import (
    ResearchPlan,
    ResearchRequest,
    ResearchStatus,
)
from backend.app.schemas.sources import ResearchSource, SearchResult
from backend.app.services.research.retrieval import ResearchRetrievalService
from backend.app.services.research.source_processor import SourceProcessor
from backend.app.services.search.base import SearchTimeoutError, SearchUnavailableError


class FakeSearchProvider:
    def __init__(self, fail_query: str | None = None, delay: float = 0) -> None:
        self.fail_query = fail_query
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.queries: list[str] = []

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        self.queries.append(query)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if query == self.fail_query:
                raise SearchTimeoutError
            return [
                SearchResult(
                    title=f"Result for {query}",
                    url="https://example.org/shared",
                    snippet="Search result snippet",
                    metadata={"query": query},
                ),
                SearchResult(url=f"https://example.org/{len(self.queries)}"),
            ][:limit]
        finally:
            self.active -= 1


def make_plan(count: int = 3) -> ResearchPlan:
    request = ResearchRequest(question="How is AI changing financial services?")
    return ResearchPlan(
        topic=request.question,
        sub_questions=[
            {"id": f"q{index}", "question": f"What evidence addresses topic area {index}?"}
            for index in range(1, count + 1)
        ],
        generated_by="llm",
    )


def test_source_processor_preserves_metadata_and_deduplicates_urls():
    processor = SourceProcessor()
    first = SearchResult(
        title="First",
        url="https://EXAMPLE.org/article?q=1",
        metadata={"engine": "one"},
    )
    duplicate = SearchResult(
        title="Duplicate",
        url="https://example.org/article?q=1",
        metadata={"engine": "two"},
    )
    source = processor.process([first, duplicate], "original search question")

    assert len(source) == 1
    assert source[0].url == "https://EXAMPLE.org/article?q=1"
    assert source[0].title == "First"
    assert source[0].publication_date is None
    assert source[0].original_query == "original search question"
    assert source[0].metadata == {"engine": "one"}
    assert source[0].retrieved_at.tzinfo is not None


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:password@example.org/",
        "not a URL",
    ],
)
def test_source_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        SearchResult(url=url)


@pytest.mark.parametrize(
    "values",
    [
        {"title": "t" * 501},
        {"snippet": "s" * 4001},
        {"url": f"https://example.org/{'x' * 2048}"},
        {"source_type": "s" * 65},
        {"metadata": {f"key-{index}": "value" for index in range(21)}},
        {"metadata": {"oversized": "m" * 501}},
        {"metadata": {"nested": {"unbounded": "value"}}},
    ],
)
def test_search_result_rejects_unbounded_source_fields(values):
    payload = {"url": "https://example.org/source", **values}
    with pytest.raises(ValueError):
        SearchResult(**payload)


def test_research_source_enforces_source_data_limits():
    with pytest.raises(ValueError):
        ResearchSource(
            source_id="src",
            title="T" * 501,
            url="https://example.org/source",
            original_query="A valid research query",
        )
    with pytest.raises(ValueError):
        ResearchSource(
            source_id="src",
            description="S" * 4001,
            url="https://example.org/source",
            original_query="A valid research query",
        )


def test_retrieval_searches_all_subquestions_and_deduplicates_globally():
    provider = FakeSearchProvider()
    service = ResearchRetrievalService(provider, SourceProcessor(), 5, 2)

    response = asyncio.run(
        service.retrieve(uuid4(), "How is AI changing financial services?", make_plan())
    )

    assert len(provider.queries) == 3
    assert len(response.sources) == 4
    assert response.status == ResearchStatus.COMPLETED
    assert len(response.query_results) == 3
    assert all(item.succeeded and item.result_count == 2 for item in response.query_results)
    assert all(
        item.error_code is None and item.error_message is None for item in response.query_results
    )
    assert response.sources[0].original_query == provider.queries[0]
    assert response.sources[1].original_query == provider.queries[0]


def test_retrieval_limits_concurrent_searches():
    provider = FakeSearchProvider(delay=0.01)
    service = ResearchRetrievalService(provider, SourceProcessor(), 5, 2)

    asyncio.run(service.retrieve(uuid4(), "How is AI changing financial services?", make_plan(5)))

    assert provider.max_active <= 2


def test_retrieval_returns_partial_failures_without_hiding_them():
    plan = make_plan(2)
    provider = FakeSearchProvider(fail_query=plan.sub_questions[0].question)
    service = ResearchRetrievalService(provider, SourceProcessor(), 5, 2)

    response = asyncio.run(
        service.retrieve(uuid4(), "How is AI changing financial services?", plan)
    )

    assert response.status == ResearchStatus.PARTIAL
    assert len(response.failures) == 1
    assert response.failures[0].code == "search_timeout"
    assert len(response.sources) > 0
    failed = [item for item in response.query_results if not item.succeeded]
    successful = [item for item in response.query_results if item.succeeded]
    assert len(failed) == 1
    assert failed[0].error_code == "search_timeout"
    assert failed[0].error_message == "The search provider request timed out."
    assert len(successful) == 1


def test_retrieval_fails_explicitly_when_all_searches_fail():
    plan = make_plan(2)
    provider = FakeSearchProvider(fail_query=plan.sub_questions[0].question)
    provider.fail_query = None

    class Unavailable:
        async def search(self, query, limit):
            raise SearchUnavailableError

    service = ResearchRetrievalService(Unavailable(), SourceProcessor(), 5, 2)

    with pytest.raises(SearchUnavailableError):
        asyncio.run(service.retrieve(uuid4(), "How is AI changing financial services?", plan))


def test_retrieval_returns_all_failure_diagnostics_for_workflow_mode():
    class Unavailable:
        async def search(self, query, limit):
            raise SearchUnavailableError

    plan = make_plan(3)
    service = ResearchRetrievalService(Unavailable(), SourceProcessor(), 5, 2)

    response = asyncio.run(
        service.retrieve(
            uuid4(),
            "How is AI changing financial services?",
            plan,
            raise_on_complete_failure=False,
        )
    )

    assert response.status == ResearchStatus.FAILED
    assert response.sources == []
    assert len(response.query_results) == 3
    assert all(not item.succeeded for item in response.query_results)
    assert all(item.result_count == 0 for item in response.query_results)
    assert all(item.error_code == "search_unavailable" for item in response.query_results)
    assert all("localhost" not in item.error_message for item in response.query_results)


def test_empty_search_results_are_success_not_provider_failure():
    class EmptyResults:
        async def search(self, query, limit):
            return []

    plan = make_plan(2)
    service = ResearchRetrievalService(EmptyResults(), SourceProcessor(), 5, 2)

    response = asyncio.run(
        service.retrieve(uuid4(), "How is AI changing financial services?", plan)
    )

    assert response.status == ResearchStatus.COMPLETED
    assert response.sources == []
    assert all(item.succeeded and item.result_count == 0 for item in response.query_results)
