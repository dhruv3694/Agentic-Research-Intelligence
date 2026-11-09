from typing import Protocol

from backend.app.schemas.llm import InstalledModel


class LLMProviderError(Exception):
    """Base class for errors raised by language model providers."""

    code = "provider_error"
    status_code = 502
    public_message = "The language model provider returned an error."


class RuntimeUnavailableError(LLMProviderError):
    code = "runtime_unavailable"
    status_code = 503
    public_message = "The local language model runtime is unavailable."


class ModelNotFoundError(LLMProviderError):
    code = "model_not_found"
    status_code = 404
    public_message = "The configured language model is not installed."


class ProviderTimeoutError(LLMProviderError):
    code = "provider_timeout"
    status_code = 504
    public_message = "The language model request timed out."


class UpstreamError(LLMProviderError):
    code = "upstream_error"
    status_code = 502
    public_message = "The language model runtime could not complete the request."


class InvalidProviderResponseError(LLMProviderError):
    code = "invalid_provider_response"
    status_code = 502
    public_message = "The language model runtime returned an invalid response."


class EmptyGenerationError(LLMProviderError):
    code = "empty_generation"
    status_code = 502
    public_message = "The language model returned an empty response."


class LLMProvider(Protocol):
    async def check_connection(self) -> bool: ...

    async def list_models(self) -> list[InstalledModel]: ...

    async def generate(
        self,
        prompt: str,
        temperature: float | None,
        max_tokens: int,
    ) -> tuple[str, bool, int]: ...
