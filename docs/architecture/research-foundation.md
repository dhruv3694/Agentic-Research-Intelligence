# Research planning and retrieval foundation

## Boundaries

- **Planning** validates the research question and decomposes it into focused
  sub-questions. It asks the existing LLM provider for a constrained JSON plan.
  If the runtime is unavailable or the output is malformed, a deterministic
  template planner is used and the response explicitly labels the fallback
  reason. A fallback is never represented as LLM output.
- **Search/retrieval** submits each sub-question to the configured
  `SearchProvider`. The initial adapter calls a separately hosted SearXNG JSON
  endpoint. Search is disabled by default; it does not invent search results.
- **Source processing** validates HTTP(S) source links, preserves their
  original URL and available metadata, assigns stable IDs, records retrieval
  time/query, and removes exact URL duplicates (case-insensitive scheme/host,
  while preserving path, query, and fragment).

## Request flow

1. `POST /api/v1/research/plan` validates a `ResearchRequest` and calls
   `ResearchPlanner`, returning an ID, plan, and `planned` status.
2. The caller submits the ID, question, and plan to
   `POST /api/v1/research/retrieve`.
3. `ResearchRetrievalService` searches sub-questions concurrently under an
   `asyncio.Semaphore`, with per-provider timeout configuration.
4. Search results are normalized and deduplicated. Partial provider failures
   are listed explicitly; if every query fails, a sanitized provider error is
   returned.

## Safety and limitations

The backend validates configured SearXNG origins and result URLs. Source URLs
are only returned as data: this phase does not fetch or crawl them, so results
cannot trigger server-side requests to arbitrary URLs. The SearXNG origin is
operator configuration and should point to a trusted instance. Do not expose a
private instance to untrusted callers without appropriate access controls.

SearXNG is an optional separately deployed service and is licensed under
AGPL-3.0. Its JSON API must be enabled in the instance configuration. Search
engines queried by SearXNG have their own terms and policies.

This phase does not persist research state, verify evidence, crawl pages,
generate citation-backed reports, use embeddings/vector databases, or
orchestrate agents.
