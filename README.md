# Agentic Research Intelligence

Agentic Research Intelligence is an open-source research platform for planning, gathering, verifying, and summarizing evidence from the web and structured sources. This repository establishes the initial Python backend foundation for the project.

## Project status

Phase 1 focuses on the backend foundation:

- FastAPI application scaffold
- Centralized configuration using Pydantic Settings
- Health checks and application metadata
- Logging configuration
- Pytest-based backend testing
- Ruff linting and formatting support

## Repository structure

```text
agentic-research-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── schemas/
│   │   ├── services/
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
