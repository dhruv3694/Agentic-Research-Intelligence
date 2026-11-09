# Agentic Research Intelligence

Agentic Research Intelligence is an open-source research platform for planning, gathering, verifying, and summarizing evidence from the web and structured sources. This repository includes a FastAPI backend foundation and a local Ollama LLM integration.

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

Research agents, RAG, and multi-agent orchestration are not implemented yet.

## Repository structure

```text
agentic-research-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   └── llm/
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
- [ ] Phase 3: Research planning and retrieval foundations


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
