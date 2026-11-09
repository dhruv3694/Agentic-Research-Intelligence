from backend.app.schemas.llm import InstalledModel
from backend.app.services.llm.base import LLMProvider, LLMProviderError


class LLMManager:
    def __init__(self, provider: LLMProvider, configured_model: str) -> None:
        self._provider = provider
        self._configured_model = configured_model

    async def status(self) -> dict[str, str | bool | None]:
        try:
            models = await self._provider.list_models()
        except LLMProviderError:
            return {
                "runtime_status": "unavailable",
                "connection_available": False,
                "configured_model": self._configured_model,
                "model_installed": None,
                "message": "The local language model runtime is unavailable.",
            }

        installed = any(
            model.name == self._configured_model or model.model == self._configured_model
            for model in models
        )
        return {
            "runtime_status": "available",
            "connection_available": True,
            "configured_model": self._configured_model,
            "model_installed": installed,
            "message": (
                "Configured model is ready."
                if installed
                else "Runtime is available, but the configured model is not installed."
            ),
        }

    async def list_models(self) -> list[InstalledModel]:
        return await self._provider.list_models()

    async def generate(
        self,
        prompt: str,
        temperature: float | None,
        max_tokens: int,
    ) -> dict[str, str | bool | int]:
        response, done, generation_time_ms = await self._provider.generate(
            prompt,
            temperature,
            max_tokens,
        )
        return {
            "model": self._configured_model,
            "response": response,
            "done": done,
            "generation_time_ms": generation_time_ms,
        }
