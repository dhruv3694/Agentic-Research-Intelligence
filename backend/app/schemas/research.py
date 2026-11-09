import re
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.schemas.sources import ResearchSource


class ResearchStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    PARTIAL = "partial"


class ResearchRequest(BaseModel):
    question: str = Field(min_length=8, max_length=2000)
    max_subquestions: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 8 or len(re.findall(r"[^\W_]+", normalized)) < 2:
            raise ValueError("question must contain at least two words")
        return normalized


class ResearchSubQuestion(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    question: str = Field(min_length=5, max_length=500)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 5:
            raise ValueError("sub-question must contain at least five characters")
        return normalized


class ResearchPlan(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    sub_questions: list[ResearchSubQuestion] = Field(min_length=1, max_length=10)
    generated_by: Literal["llm", "deterministic_fallback"]
    fallback_reason: Literal["llm_unavailable", "invalid_llm_output"] | None = None

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("topic must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_unique_sub_questions(self) -> "ResearchPlan":
        normalized = [item.question.casefold().strip(" ?!.") for item in self.sub_questions]
        if len(normalized) != len(set(normalized)):
            raise ValueError("sub_questions must not contain duplicates")
        if self.generated_by == "llm" and self.fallback_reason is not None:
            raise ValueError("LLM-generated plans cannot include a fallback reason")
        if self.generated_by == "deterministic_fallback" and self.fallback_reason is None:
            raise ValueError("fallback plans must include a fallback reason")
        return self


class ResearchPlanResponse(BaseModel):
    research_id: UUID
    question: str
    plan: ResearchPlan
    status: ResearchStatus = ResearchStatus.PLANNED


class ResearchRetrievalRequest(BaseModel):
    research_id: UUID
    question: str = Field(min_length=8, max_length=2000)
    plan: ResearchPlan

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 8 or len(re.findall(r"[^\W_]+", normalized)) < 2:
            raise ValueError("question must contain at least two words")
        return normalized


class SearchFailure(BaseModel):
    query: str
    code: str
    message: str


class ResearchRetrievalResponse(BaseModel):
    research_id: UUID
    question: str
    plan: ResearchPlan
    status: ResearchStatus
    sources: list[ResearchSource]
    failures: list[SearchFailure] = Field(default_factory=list)
