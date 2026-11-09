import logging
import time

import httpx
from pydantic import ValidationError

from backend.app.schemas.llm import InstalledModel, OllamaGeneratePayload, OllamaModelsPayload
from backend.app.services.llm.base import (
    EmptyGenerationError,
    InvalidProviderResponseError,
    ModelNotFoundError,
    ProviderTimeoutError,
    RuntimeUnavailableError,
    UpstreamError,
)

logger = logging.getLogger(__name__)


class OllamaProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        model: str,
        temperature: float,
        num_ctx: int,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._num_ctx = num_ctx

    async def check_connection(self) -> bool:
        try:
            await self.list_models()
        except RuntimeUnavailableError:
            return False
        return True

    async def list_models(self) -> list[InstalledModel]:
        response = await self._request("GET", "/api/tags")
        try:
            payload = OllamaModelsPayload.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise InvalidProviderResponseError from exc
        return payload.models

    async def generate(
        self,
        prompt: str,
        temperature: float | None,
        max_tokens: int,
    ) -> tuple[str, bool, int]:
        models = await self.list_models()
        if not any(model.name == self._model or model.model == self._model for model in models):
            raise ModelNotFoundError

        options: dict[str, int | float] = {
            "temperature": temperature if temperature is not None else self._temperature,
            "num_ctx": self._num_ctx,
        }
        options["num_predict"] = max_tokens

        started = time.perf_counter()
        response = await self._request(
            "POST",
            "/api/generate",
            json={
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": options,
            },
        )
        generation_time_ms = round((time.perf_counter() - started) * 1000)
        try:
            payload = OllamaGeneratePayload.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise InvalidProviderResponseError from exc

        if not payload.response.strip():
            raise EmptyGenerationError
        return payload.response, payload.done, generation_time_ms

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            logger.warning("Ollama request timed out (%s).", type(exc).__name__)
            raise ProviderTimeoutError from exc
        except httpx.ConnectError as exc:
            logger.warning("Could not connect to Ollama (%s).", type(exc).__name__)
            raise RuntimeUnavailableError from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("Ollama returned HTTP %s.", exc.response.status_code)
            if exc.response.status_code == 404 and path == "/api/generate":
                raise ModelNotFoundError from exc
            raise UpstreamError from exc
        except httpx.RequestError as exc:
            logger.warning("Ollama request failed (%s).", type(exc).__name__)
            raise RuntimeUnavailableError from exc
