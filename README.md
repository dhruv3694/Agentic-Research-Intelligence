# Agentic Research Intelligence

Agentic Research Intelligence is an open-source research platform for planning, gathering, verifying, and summarizing evidence from the web and structured sources. This repository includes a FastAPI backend with local Ollama integration and a LangGraph research workflow.

## Project status

### Phase 1 — Backend foundation (complete)

- FastAPI application scaffold
- Centralized configuration using Pydantic Settings
- Health checks and application metadata
- Logging configuration
- Pytest-based backend testing
- Ruff linting and formatting support

### Phase 2 — Local LLM integration (implemented)

- Provider-neutral LLM service interface
- Ollama status, model-listing, and generation endpoints
- Mocked HTTP tests; no Ollama runtime is required for CI

### Phase 3 — Research planning and retrieval foundation (complete; mocked validation)

- Research plans use the configured Ollama model when available and a clearly
  labeled deterministic fallback when it is unavailable.
- Optional search and source normalization use a provider interface. SearXNG
  is the initial adapter; search is disabled by default.
- Retrieval searches planned sub-questions concurrently with a configurable
  bound and deduplicates results without fetching source URLs.
- The standalone planning and retrieval endpoints are also available for clients
  that want to inspect or run those steps separately.

### Phase 4 — LangGraph research workflow (implemented; mocked validation)

- `POST /api/v1/research/run` composes planner, researcher, analyst, verifier,
  report-preparation, and supervisor roles in a real LangGraph `StateGraph`.
- The response exposes shared workflow state and per-stage execution history;
  verifier-directed targeted research is capped at one retry.
- Supported and partially supported claims require unique source references;
  conflicting claims preserve references to at least two retrieved sources.
- Per-query search outcomes and sanitized errors are included in the response.
- Workflow execution is capped by `RESEARCH_WORKFLOW_TIMEOUT` (default 300
  seconds; maximum 600). Source title, snippet, URL, source type, and metadata
  are bounded by schema limits; SearXNG text truncation is marked in metadata.
- Workflow state is in-memory per request. Checkpointing, durable history,
  resume, page crawling, and independent source/citation verification are not
  implemented.

## Repository structure

```text
agentic-research-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── llm/
│   │   │   ├── orchestration/
│   │   │   ├── research/
│   │   │   └── search/
│   │   ├── __init__.py
│   │   └── main.py
│   └── tests/
├── docs/
├── frontend/
├── models/
├── evaluation/
├── tests/
├── .github/
├── .env.example
├── .gitignore
├── .python-version
├── LICENSE
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── requirements.txt
└── pyproject.toml
```

## Python environment

This project targets Python 3.11.

### Create a virtual environment

PowerShell:

```powershell
cd "C:\Users\DHRUV\Desktop\Agentic Research Intelligence"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Activate later

```powershell
cd "C:\Users\DHRUV\Desktop\Agentic Research Intelligence"
.\.venv\Scripts\Activate.ps1
```

## Run the backend

```powershell
cd "C:\Users\DHRUV\Desktop\Agentic Research Intelligence"
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open:

- http://localhost:8000/
- http://localhost:8000/api/v1/health
- http://localhost:8000/docs
- http://localhost:8000/api/v1/llm/status

## Local LLM integration

Ollama is used as the initial inference runtime because it exposes a local HTTP
API and supports open-weight models without a paid inference service. The
backend uses a provider interface so other local or open-weight runtimes can be
added without changing the API endpoints.

The default model is `qwen3:4b`, whose model card declares the Apache-2.0
license. Model licensing and usage terms can vary; review the model's license
before use or redistribution. The project does not redistribute model weights.
The model can be changed with `OLLAMA_MODEL`.

Install Ollama from [ollama.com/download](https://ollama.com/download), then
explicitly pull the model when ready. Model weights require a multi-gigabyte
download; neither installation nor model download happens when running this
backend.

```powershell
ollama pull qwen3:4b
Copy-Item .env.example .env
```

See [Local LLM setup](docs/development/local-llm-setup.md) for detailed
PowerShell instructions and [LLM architecture](docs/architecture/llm-integration.md)
for the provider design.

## Research planning and retrieval

Planning and retrieval can be called separately or as part of the end-to-end
LangGraph workflow. `POST /api/v1/research/plan`
returns an LLM-generated or explicitly marked deterministic fallback plan.
`POST /api/v1/research/retrieve` accepts that plan and searches each
sub-question through the configured provider, normalizes sources, and
deduplicates URLs. The workflow at `POST /api/v1/research/run` composes those
services with structured analysis, verification, and deterministic report
preparation; it does not crawl source pages.

Search is disabled by default; without an external search instance, retrieval
returns a clear `search_unavailable` error and never fabricates results.
SearXNG is an optional self-hosted adapter. SearXNG is licensed under
AGPL-3.0 and requires a separately deployed instance; see the [Search provider
setup guide](docs/development/search-provider-setup.md). Consult the
[research architecture](docs/architecture/research-foundation.md) for the
planning, retrieval, and source-processing boundaries, and the [agentic
workflow architecture](docs/architecture/agentic-workflow.md) for graph
routing, evidence limitations, and the workflow API.

To run the composed workflow:

```powershell
$body = @{
    question = "How is generative AI changing financial services?"
    max_subquestions = 5
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
    -Uri http://localhost:8000/api/v1/research/run `
    -ContentType "application/json" `
    -Body $body
```

Successful runs require an available configured Ollama model and a configured
search provider. Failures are returned as an inspectable workflow response.
Analysis uses search-result snippets, not fetched pages; verification is not
independent fact-checking. State does not persist across requests or restarts.

Workflow statuses mean:

- `completed`: the graph finished without partial retrieval or unresolved
  evidence classifications.
- `partial`: the graph finished with partial retrieval, empty evidence,
  partially supported, unsupported, or conflicting findings, or research gaps.
- `failed`: an essential stage failed, all initial searches failed, or the
  execution deadline expired.

Each `retrieval_diagnostics` entry reports the query, success flag, result
count, and sanitized error category/message when a query failed. A successful
query returning no results is not itself a provider failure. Set
`RESEARCH_WORKFLOW_TIMEOUT` in `.env` to configure the overall deadline; it
covers retries as well as the initial plan and analysis.

Example planning request:

```powershell
$plan = Invoke-RestMethod -Method Post `
    -Uri http://localhost:8000/api/v1/research/plan `
    -ContentType "application/json" `
    -Body (@{
        question = "How is generative AI changing the FinTech industry?"
        max_subquestions = 5
    } | ConvertTo-Json)
$plan
```

Once a search provider is configured, retrieve sources using the returned plan:

```powershell
$retrieval = @{
    research_id = $plan.research_id
    question = $plan.question
    plan = $plan.plan
} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Method Post `
    -Uri http://localhost:8000/api/v1/research/retrieve `
    -ContentType "application/json" `
    -Body $retrieval
```

### API examples

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/llm/status
Invoke-RestMethod http://localhost:8000/api/v1/llm/models

$body = @{
    prompt = "Explain how transformer attention works."
    temperature = 0.2
    max_tokens = 512
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
    -Uri http://localhost:8000/api/v1/llm/generate `
    -ContentType "application/json" `
    -Body $body
```

Generation API responses include a wall-clock generation duration measured by
the backend. Prompts are not logged by the application.

### Roadmap

- [x] Phase 1: Python backend foundation
- [x] Phase 2: Local Ollama integration (verified by mocked tests)
- [x] Phase 3: Research planning and retrieval foundations (verified by mocked tests)
- [x] Phase 4: LangGraph orchestration and run API (verified by mocked tests)


## Testing

```powershell
cd "C:\Users\DHRUV\Desktop\Agentic Research Intelligence"
.\.venv\Scripts\Activate.ps1
pytest -q
```

## Linting

```powershell
cd "C:\Users\DHRUV\Desktop\Agentic Research Intelligence"
.\.venv\Scripts\Activate.ps1
ruff check .
```

## Contributing

Please review [CONTRIBUTING.md](CONTRIBUTING.md) for development practices and contribution guidelines.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
