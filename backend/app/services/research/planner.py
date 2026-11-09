import json
import logging
import re
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError

from backend.app.schemas.research import ResearchPlan, ResearchRequest, ResearchSubQuestion
from backend.app.services.llm.base import LLMProviderError

logger = logging.getLogger(__name__)


class PlanGenerator(Protocol):
    async def generate(
        self,
        prompt: str,
        temperature: float | None,
        max_tokens: int,
    ) -> tuple[str, bool, int]: ...


class GeneratedPlan(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    sub_questions: list[str] = Field(min_length=1, max_length=20)


class ResearchPlanner:
    def __init__(self, generator: PlanGenerator, default_max_subquestions: int = 5) -> None:
        self._generator = generator
        self._default_max_subquestions = default_max_subquestions

    async def create_plan(self, request: ResearchRequest) -> ResearchPlan:
        limit = min(request.max_subquestions, self._default_max_subquestions)
        prompt = (
            "Create a concise research plan. Return only a JSON object with a string "
            '"topic" and a "sub_questions" array of distinct, focused question strings. '
            f"Include at most {limit} questions. Do not provide sources or claim findings.\n"
            f"Research question: {request.question}"
        )
        try:
            generated_text, done, _ = await self._generator.generate(prompt, 0.2, 700)
        except LLMProviderError as exc:
            logger.info("Using deterministic research planning fallback (%s).", exc.code)
            return self._fallback(request.question, limit, "llm_unavailable")

        try:
            if not done:
                raise ValueError("LLM generation did not complete")
            generated = GeneratedPlan.model_validate(json.loads(generated_text))
            sub_questions = self._unique_questions(generated.sub_questions, limit)
            if not sub_questions:
                raise ValueError("LLM plan contained no usable sub-questions")
            return ResearchPlan(
                topic=generated.topic.strip(),
                sub_questions=sub_questions,
                generated_by="llm",
            )
        except (json.JSONDecodeError, ValidationError, ValueError):
            logger.info("Using deterministic research planning fallback (invalid output).")
            return self._fallback(request.question, limit, "invalid_llm_output")

    def _fallback(
        self,
        question: str,
        limit: int,
        reason: str,
    ) -> ResearchPlan:
        topic = self._extract_topic(question)
        templates = [
            f"What are the current applications and use cases of {topic}?",
            f"What benefits and opportunities are associated with {topic}?",
            f"What challenges, risks, or limitations affect {topic}?",
            f"What evidence and examples describe the impact of {topic}?",
            f"What trends and future developments are shaping {topic}?",
        ]
        questions = self._unique_questions(templates, limit)
        return ResearchPlan(
            topic=topic,
            sub_questions=questions,
            generated_by="deterministic_fallback",
            fallback_reason=reason,
        )

    @staticmethod
    def _extract_topic(question: str) -> str:
        topic = question.strip().rstrip("?.! ")
        topic = re.sub(
            r"^(?:how|what|why|when|where|which|who)\s+(?:is|are|does|do|did|can|could|will|would)\s+",
            "",
            topic,
            flags=re.IGNORECASE,
        )
        return topic.strip() or question.strip()

    @staticmethod
    def _unique_questions(
        questions: list[str],
        limit: int,
    ) -> list[ResearchSubQuestion]:
        unique: list[ResearchSubQuestion] = []
        seen: set[str] = set()
        for question in questions:
            normalized = " ".join(question.split()).strip(" ?!.")
            key = normalized.casefold()
            if len(normalized) < 5 or key in seen:
                continue
            seen.add(key)
            unique.append(
                ResearchSubQuestion(id=f"q{len(unique) + 1}", question=normalized.rstrip("?") + "?")
            )
            if len(unique) >= limit:
                break
        return unique
