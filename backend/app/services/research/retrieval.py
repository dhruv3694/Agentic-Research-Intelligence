import asyncio
import logging
from uuid import UUID

from backend.app.schemas.research import (
    ResearchPlan,
    ResearchRetrievalResponse,
    ResearchStatus,
    SearchFailure,
)
from backend.app.schemas.sources import SearchResult
from backend.app.services.research.source_processor import SourceProcessor
from backend.app.services.search.base import SearchProvider, SearchProviderError

logger = logging.getLogger(__name__)


class ResearchRetrievalService:
    def __init__(
        self,
        search_provider: SearchProvider,
        source_processor: SourceProcessor,
        max_results: int,
        max_concurrent_searches: int,
    ) -> None:
        self._search_provider = search_provider
        self._source_processor = source_processor
        self._max_results = max_results
        self._semaphore = asyncio.Semaphore(max_concurrent_searches)

    async def retrieve(
        self,
        research_id: UUID,
        question: str,
        plan: ResearchPlan,
    ) -> ResearchRetrievalResponse:
        async def search_one(
            query: str,
        ) -> tuple[str, list[SearchResult], SearchProviderError | None]:
            async with self._semaphore:
                try:
                    results = await self._search_provider.search(query, self._max_results)
                    return query, results, None
                except SearchProviderError as exc:
                    logger.info("Search failed for a research query (%s).", exc.code)
                    return query, [], exc

        searched = await asyncio.gather(
            *(search_one(subquestion.question) for subquestion in plan.sub_questions)
        )
        failures = [
            SearchFailure(query=query, code=error.code, message=error.public_message)
            for query, _, error in searched
            if error is not None
        ]
        successful = [(query, results) for query, results, error in searched if error is None]

        if failures and not successful:
            error = next(error for _, _, error in searched if error is not None)
            raise error

        normalized = []
        seen_source_ids: set[str] = set()
        for query, results in successful:
            for source in self._source_processor.process(results, query):
                if source.source_id not in seen_source_ids:
                    normalized.append(source)
                    seen_source_ids.add(source.source_id)
        return ResearchRetrievalResponse(
            research_id=research_id,
            question=question,
            plan=plan,
            status=ResearchStatus.PARTIAL if failures else ResearchStatus.COMPLETED,
            sources=normalized,
            failures=failures,
        )
