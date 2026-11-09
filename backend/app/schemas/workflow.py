from datetime import datetime
from enum import StrEnum
from typing import Literal, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.schemas.research import QueryRetrievalDiagnostic, ResearchPlan
from backend.app.schemas.sources import ResearchSource


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class WorkflowStage(StrEnum):
    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    VERIFIER = "verifier"
    REPORT = "report_preparation"
    END = "end"


class AgentExecution(BaseModel):
    agent_name: WorkflowStage
    started_at: datetime
    ended_at: datetime
    status: Literal["succeeded", "failed"]
    duration_ms: int = Field(ge=0)
    retry_count: int = Field(default=0, ge=0)
    error_code: str | None = None


class WorkflowError(BaseModel):
    stage: WorkflowStage
    code: str
    message: str


class AnalyticalFinding(BaseModel):
    finding_id: str = Field(min_length=1, max_length=40)
    group: str = Field(min_length=1, max_length=120)
    claim: str = Field(min_length=1, max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("source_ids")
    @classmethod
    def validate_unique_sources(cls, values: list[str]) -> list[str]:
        if any(not source_id.strip() for source_id in values):
            raise ValueError("source IDs must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("source IDs must be unique")
        return values


class AnalysisResult(BaseModel):
    findings: list[AnalyticalFinding] = Field(max_length=50)


class ClaimVerification(BaseModel):
    finding_id: str
    status: Literal["supported", "partially_supported", "unsupported", "conflicting"]
    rationale: str = Field(min_length=1, max_length=1000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_evidence_references(self) -> "ClaimVerification":
        if any(not source_id.strip() for source_id in self.source_ids):
            raise ValueError("source IDs must not be blank")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("source IDs must be unique")
        if self.status in {"supported", "partially_supported"} and not self.source_ids:
            raise ValueError("supported claims require at least one source")
        if self.status == "conflicting" and len(self.source_ids) < 2:
            raise ValueError("conflicting claims require at least two sources")
        return self


class VerificationResult(BaseModel):
    claims: list[ClaimVerification] = Field(max_length=50)
    research_gaps: list[str] = Field(default_factory=list, max_length=20)
    additional_queries: list[str] = Field(default_factory=list, max_length=3)
    can_retry: bool = False

    @field_validator("additional_queries")
    @classmethod
    def normalize_additional_queries(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()).strip(" ?!.") for value in values]
        if any(not 5 <= len(query) <= 500 for query in normalized):
            raise ValueError("additional queries must contain 5 to 500 characters")
        if len({query.casefold() for query in normalized}) != len(normalized):
            raise ValueError("additional queries must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_retry_queries(self) -> "VerificationResult":
        finding_ids = [claim.finding_id for claim in self.claims]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("verification finding IDs must be unique")
        if self.can_retry and not self.additional_queries:
            raise ValueError("additional_queries are required when can_retry is true")
        if not self.can_retry and self.additional_queries:
            raise ValueError("additional_queries require can_retry to be true")
        return self


class ReportSection(BaseModel):
    heading: str
    finding_ids: list[str]
    source_ids: list[str]
    finding_sources: dict[str, list[str]] = Field(default_factory=dict)


class ReportConflict(BaseModel):
    finding_id: str
    claim: str
    rationale: str
    source_ids: list[str] = Field(min_length=2, max_length=20)


class ResearchReport(BaseModel):
    title: str
    summary: str
    sections: list[ReportSection]
    conflicts: list[ReportConflict] = Field(default_factory=list)
    research_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ResearchWorkflowState(TypedDict, total=False):
    research_id: str
    question: str
    max_subquestions: int
    plan: ResearchPlan | None
    sources: list[ResearchSource]
    findings: list[AnalyticalFinding]
    verification: VerificationResult | None
    report: ResearchReport | None
    current_stage: WorkflowStage
    next_stage: WorkflowStage
    execution_history: list[AgentExecution]
    errors: list[WorkflowError]
    retrieval_partial: bool
    retrieval_diagnostics: list[QueryRetrievalDiagnostic]
    attempted_queries: list[str]
    targeted_queries: list[str]
    retry_count: int
    max_retries: int
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None
    deadline_monotonic: float


class ResearchWorkflowRunResponse(BaseModel):
    research_id: UUID
    question: str
    status: WorkflowStatus
    plan: ResearchPlan | None
    sources: list[ResearchSource]
    findings: list[AnalyticalFinding]
    verification: VerificationResult | None
    report: ResearchReport | None
    execution_history: list[AgentExecution]
    retry_count: int
    max_retries: int
    attempted_queries: list[str]
    retrieval_partial: bool
    retrieval_diagnostics: list[QueryRetrievalDiagnostic]
    started_at: datetime
    completed_at: datetime
    errors: list[WorkflowError]
