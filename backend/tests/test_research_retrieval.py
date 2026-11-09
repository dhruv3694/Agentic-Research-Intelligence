import asyncio
from uuid import uuid4

import pytest

from backend.app.schemas.research import (
    ResearchPlan,
    ResearchRequest,
    ResearchStatus,
)
from backend.app.schemas.sources import SearchResult
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


def test_retrieval_searches_all_subquestions_and_deduplicates_globally():
    provider = FakeSearchProvider()
    service = ResearchRetrievalService(provider, SourceProcessor(), 5, 2)

    response = asyncio.run(
        service.retrieve(uuid4(), "How is AI changing financial services?", make_plan())
    )

    assert len(provider.queries) == 3
    assert len(response.sources) == 4
    assert response.status == ResearchStatus.COMPLETED
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
