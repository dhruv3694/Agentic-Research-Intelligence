# Local LLM integration architecture

## Components

- `LLMProvider` defines the asynchronous provider contract: connection check,
  model listing, and text generation.
- `OllamaProvider` implements the contract using the Ollama HTTP API and a
  shared HTTPX client.
- `LLMManager` applies app-level behavior and measures generation wall time.
- `/api/v1/llm/*` endpoints validate input and serialize stable response
  schemas; they do not depend on Ollama request/response details.

## Request lifecycle

1. FastAPI lifespan creates one HTTPX `AsyncClient` with the configured base
   URL and timeout. Creating this client does not contact Ollama.
2. The lifespan constructs `OllamaProvider` and `LLMManager`, then stores the
   manager in application state.
3. API routes resolve the manager and invoke provider-independent operations.
4. The provider performs asynchronous `GET /api/tags` or
   `POST /api/generate` calls. Generation is non-streaming and uses Ollama's
   `options.temperature`, `options.num_predict` (request `max_tokens`), and
   configured `options.num_ctx`.
5. Provider output is validated before it is returned. Generation latency is
   measured with a monotonic wall-clock timer around Ollama's generation
   request, excluding model availability checks.
6. FastAPI closes the shared HTTP client on shutdown.

## Errors and privacy

Connection errors, timeouts, missing models, invalid upstream payloads, and
empty generations map to stable API error codes and appropriate HTTP statuses.
Responses do not expose upstream payloads, stack traces, or local paths.
Provider logs contain error categories/status codes only; prompt content is
not logged.

Request validation failures use HTTP 422 and a generic message, avoiding echo
of supplied prompt content. Model listing/status is independent of generation.
The app starts even if Ollama is not installed or running; availability is
checked when an LLM endpoint is called.

## Extending providers

Implement `LLMProvider` for a new runtime and inject it into `LLMManager` at
application startup. Endpoint and response-schema code need not change unless
the new runtime requires additional public capabilities. LangGraph, research
agents, RAG, and remote paid inference providers are out of scope for this
milestone.
