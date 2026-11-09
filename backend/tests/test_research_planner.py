import asyncio

import pytest
from pydantic import ValidationError

from backend.app.schemas.research import ResearchPlan, ResearchRequest
from backend.app.services.llm.base import RuntimeUnavailableError
from backend.app.services.research.planner import ResearchPlanner


class FakeGenerator:
    def __init__(
        self,
        response: str = "",
        error: Exception | None = None,
        done: bool = True,
    ) -> None:
        self.response = response
        self.error = error
        self.done = done
        self.max_tokens: int | None = None

    async def generate(self, prompt, temperature, max_tokens):
        self.max_tokens = max_tokens
        if self.error:
            raise self.error
        return self.response, self.done, 0


def test_request_normalizes_question_and_applies_defaults():
    request = ResearchRequest(question="  How is AI changing finance?  ")

    assert request.question == "How is AI changing finance?"
    assert request.max_subquestions == 5


@pytest.mark.parametrize(
    "question",
    ["", "AI", "   ?   ", "a" * 2001],
)
def test_request_rejects_empty_or_meaningless_question(question):
    with pytest.raises(ValidationError):
        ResearchRequest(question=question)


def test_request_rejects_invalid_subquestion_limit():
    with pytest.raises(ValidationError):
        ResearchRequest(question="How is AI changing finance?", max_subquestions=0)


def test_planner_uses_structured_llm_plan_and_respects_maximum():
    generator = FakeGenerator(
        '{"topic":"AI in finance","sub_questions":['
        '"What applications use AI in finance?",'
        '"What risks affect AI in finance?",'
        '"What evidence supports AI in finance?"]}'
    )
    planner = ResearchPlanner(generator, default_max_subquestions=5)

    plan = asyncio.run(
        planner.create_plan(
            ResearchRequest(question="How is AI changing finance?", max_subquestions=2)
        )
    )

    assert plan.generated_by == "llm"
    assert len(plan.sub_questions) == 2
    assert plan.topic == "AI in finance"
    assert generator.max_tokens == 700


def test_planner_removes_duplicate_llm_questions():
    generator = FakeGenerator(
        '{"topic":"AI","sub_questions":['
        '"What are the benefits of AI in finance?",'
        '"What are the benefits of AI in finance?"]}'
    )
    plan = asyncio.run(
        ResearchPlanner(generator).create_plan(
            ResearchRequest(question="What are AI finance benefits?")
        )
    )

    assert plan.generated_by == "llm"
    assert len(plan.sub_questions) == 1


def test_planner_uses_labeled_deterministic_fallback_when_llm_unavailable():
    generator = FakeGenerator(error=RuntimeUnavailableError())
    plan = asyncio.run(
        ResearchPlanner(generator).create_plan(
            ResearchRequest(question="How is AI changing finance?", max_subquestions=3)
        )
    )

    assert plan.generated_by == "deterministic_fallback"
    assert plan.fallback_reason == "llm_unavailable"
    assert len(plan.sub_questions) == 3
    assert "AI changing finance" in plan.topic


def test_planner_uses_fallback_for_malformed_llm_plan():
    generator = FakeGenerator("not valid JSON")
    plan = asyncio.run(
        ResearchPlanner(generator).create_plan(
            ResearchRequest(question="How is AI changing finance?")
        )
    )

    assert plan.generated_by == "deterministic_fallback"
    assert plan.fallback_reason == "invalid_llm_output"


def test_research_plan_rejects_duplicates_and_mislabeled_fallback():
    with pytest.raises(ValidationError):
        ResearchPlan(
            topic="AI",
            sub_questions=[
                {"id": "q1", "question": "What is AI used for?"},
                {"id": "q2", "question": "What is AI used for?"},
            ],
            generated_by="llm",
        )

    with pytest.raises(ValidationError):
        ResearchPlan(
            topic="AI",
            sub_questions=[{"id": "q1", "question": "What is AI used for?"}],
            generated_by="deterministic_fallback",
        )
