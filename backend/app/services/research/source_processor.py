import hashlib
import logging
from urllib.parse import urlsplit, urlunsplit

from backend.app.schemas.sources import ResearchSource, SearchResult

logger = logging.getLogger(__name__)


class SourceProcessor:
    def process(
        self,
        results: list[SearchResult],
        original_query: str,
    ) -> list[ResearchSource]:
        processed: list[ResearchSource] = []
        seen: set[str] = set()
        for result in results:
            source_url = result.url.strip()
            key = self._deduplication_key(source_url)
            if key in seen:
                continue
            seen.add(key)
            source_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
            processed.append(
                ResearchSource(
                    source_id=source_id,
                    title=result.title,
                    url=source_url,
                    description=result.snippet,
                    source_type=result.source_type,
                    publication_date=result.publication_date,
                    original_query=original_query,
                    metadata=result.metadata,
                )
            )
        return processed

    @staticmethod
    def _deduplication_key(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                parts.path,
                parts.query,
                parts.fragment,
            )
        )
