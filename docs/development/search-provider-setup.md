# Search provider setup

Search is disabled by default. The research planning API remains usable without
a search server, but `/api/v1/research/retrieve` returns a sanitized
`search_unavailable` error until a provider is configured.

## Provider selection and license

The project defines a provider-independent asynchronous search interface.
SearXNG is the initial adapter because it is open-source, self-hostable, and
offers a JSON HTTP search API. SearXNG is licensed under
[AGPL-3.0](https://raw.githubusercontent.com/searxng/searxng/master/LICENSE).
It is a separate service, not a Python dependency or part of this repository.
Operators should understand the license and network-service obligations before
deploying or modifying it. SearXNG itself queries configured upstream search
engines, each with separate terms.

The adapter follows the official [SearXNG Search API
documentation](https://docs.searxng.org/dev/search_api.html): GET `/search`
with `q` and `format=json`. JSON output must be enabled in the instance's
`settings.yml`; public instances often disable it.

## Start a local SearXNG instance (optional)

These commands follow the official [container installation
guide](https://docs.searxng.org/admin/installation-docker.html). They require
Docker Desktop and download container images. They are optional and are not
run by this project.

```powershell
$instance = Join-Path $env:USERPROFILE "searxng-instance"
New-Item -ItemType Directory -Force (Join-Path $instance "core-config") | Out-Null
Set-Location $instance
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/searxng/searxng/master/container/docker-compose.yml" `
  -OutFile "docker-compose.yml"
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/searxng/searxng/master/container/.env.example" `
  -OutFile ".env.example"
Copy-Item ".env.example" ".env"
docker compose up -d
```

Review the downloaded compose template and `.env` before starting containers.
Configure JSON output in the SearXNG instance's `core-config/settings.yml`
according to the official docs. Verify the API response:

```powershell
Invoke-RestMethod "http://localhost:8080/search?q=FinTech&format=json"
```

Stop the optional service when finished:

```powershell
Set-Location $instance
docker compose down
```

## Configure this backend

At the repository root, edit the ignored local `.env` file:

```powershell
$envFile = ".env"
if (-not (Test-Path $envFile)) { Copy-Item ".env.example" $envFile }
```

Set these values in `.env`:

```dotenv
SEARCH_PROVIDER=searxng
SEARXNG_BASE_URL=http://localhost:8080
SEARCH_TIMEOUT=15
SEARCH_MAX_RESULTS=5
RESEARCH_MAX_SUBQUESTIONS=5
RESEARCH_MAX_CONCURRENT_SEARCHES=3
```

Restart the API and submit a research plan then a retrieval request. No search
credentials are required by the local adapter. Do not place secrets in
`.env.example` or commit a real `.env`.

## Errors and privacy

- `search_unavailable`: search is disabled or the configured instance cannot
  be reached.
- `search_timeout`: the provider did not respond within `SEARCH_TIMEOUT`.
- `invalid_search_response`: the JSON response did not match the API shape.
- `search_provider_error`: the server rejected the request, such as when JSON
  output is disabled.

Search queries are sent to the configured SearXNG instance and may be forwarded
to that instance's configured upstream engines. Do not send sensitive research
questions unless your deployment and upstream configuration are appropriate.
The backend does not log query content, fetch returned URLs, or persist results.
