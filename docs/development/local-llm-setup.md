# Local LLM setup

The backend talks to a local Ollama server over HTTP. Starting the FastAPI
application does not install Ollama, download weights, or require Ollama to be
running.

## Machine and model considerations

The development machine used to verify this integration has 15.2 GB system RAM
and no GPU was detected. Qwen3 4B is a reasonable small-model starting point
for CPU inference on this hardware, but inference may be slow and actual memory
requirements depend on quantization, context length, and other running
applications. Use a smaller Ollama model if memory or latency is unacceptable.

The default `qwen3:4b` model is identified as Apache-2.0 licensed in its model
card. Review the [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B)
and its license before using or redistributing it. The model weights are
distributed separately from this repository and are not included here.

## Install and run Ollama

Install Ollama from its official [Windows download page](https://ollama.com/download).
Installation and model download are system-level/user-controlled actions and
are intentionally not performed by this project.

In PowerShell, confirm Ollama is available and explicitly download the default
model (the download is several gigabytes):

```powershell
ollama --version
ollama pull qwen3:4b
ollama list
```

Ollama serves its local HTTP API at `http://localhost:11434` by default.
Confirm the runtime directly if needed:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

## Configure and run this backend

From the repository root:

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Adjust the `.env` values as needed:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP API origin |
| `OLLAMA_MODEL` | `qwen3:4b` | Model name returned by Ollama |
| `OLLAMA_TIMEOUT` | `120` | HTTP timeout in seconds |
| `OLLAMA_TEMPERATURE` | `0.2` | Default generation temperature (0 to 2) |
| `OLLAMA_NUM_CTX` | `4096` | Context window configured for generation |

Other supported settings include `APP_NAME`, `APP_VERSION`, `APP_ENV`, `DEBUG`,
`API_HOST`, `API_PORT`, and `LOG_LEVEL`. Do not put credentials in the
environment sample or commit a real `.env` file.

## Check and generate

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

`max_tokens` is mapped to Ollama's `options.num_predict`; the configured
context length is sent as `options.num_ctx`. Generation uses non-streaming
mode.

## Troubleshooting

- **Runtime unavailable:** Start Ollama and verify the configured base URL with
  `Invoke-RestMethod http://localhost:11434/api/tags`.
- **Model not found:** Run `ollama list` and ensure the listed model name
  matches `OLLAMA_MODEL`, or pull the selected model explicitly.
- **Request timeout:** Reduce the prompt/token limit, use a smaller model, or
  increase `OLLAMA_TIMEOUT` for slow local inference.
- **Out of memory or very slow generation:** Choose a smaller/quantized model
  and/or lower `OLLAMA_NUM_CTX`; avoid downloading weights until you have
  checked their size and terms.

The API does not include prompts in logs and returns sanitized provider errors.

## Runtime and dependency licenses

The Qwen3-4B model is Apache-2.0 licensed according to its model card. Ollama
is a separately installed runtime; review its [license](https://github.com/ollama/ollama/blob/main/LICENSE)
and the selected model's terms before use. Model files are not redistributed
by this project.

Phase 2 adds no Python dependencies: HTTPX was already pinned in
`requirements.txt` and is used for asynchronous HTTP. The existing direct
dependencies are distributed under their respective licenses: FastAPI,
Pydantic, pydantic-settings, pytest, and Ruff are MIT or MIT/Apache-2.0;
Uvicorn, python-dotenv, and HTTPX are BSD-3-Clause. Consult each package's
license file and installed version metadata for authoritative terms.
