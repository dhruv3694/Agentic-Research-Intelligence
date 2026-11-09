# Developing workflow agents

Workflow roles are implemented in
`backend/app/services/orchestration/agents.py`; graph nodes and routing live in
`backend/app/services/orchestration/workflow.py`. Shared state and API output
models are defined in `backend/app/schemas/workflow.py`.

## Adding or changing an agent

1. Define the role's input/output boundary and validate generated data with a
   Pydantic schema. Treat model responses as untrusted; do not accept source IDs
   that are not present in the input evidence.
2. Implement the role in `agents.py`, reusing the existing planner, retrieval,
   and LLM interfaces where applicable. Convert expected provider failures into
   `AgentExecutionError` with a safe public message.
3. Add a graph node in `ResearchWorkflow`, return only the fields that node
   updates, and add its supervisor route and graph edge.
4. Update the shared-state and workflow architecture documentation when fields,
   routing, retries, or persistence behavior changes.
5. Add mocked tests for successful output, malformed output, provider failure,
   and routing/termination behavior. Never require live Ollama or search
   services in unit tests.

Run the backend tests and Ruff checks from the repository root:

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
```

Keep retries bounded and ensure duplicate queries cannot create loops. The
current workflow has one targeted research retry and no durable checkpoints or
resume behavior.
