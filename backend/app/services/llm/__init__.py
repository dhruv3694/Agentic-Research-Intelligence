"""Provider-independent local language model services."""

from backend.app.services.llm.manager import LLMManager
from backend.app.services.llm.ollama_provider import OllamaProvider

__all__ = ["LLMManager", "OllamaProvider"]
