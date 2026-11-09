import asyncio
import json
from uuid import UUID

from backend.app.schemas.research import (
    ResearchPlan,
    ResearchRetrievalResponse,
    ResearchStatus,
    ResearchSubQuestion,
)
from backend.app.schemas.sources import ResearchSource
from backend.app.schemas.workflow import WorkflowStage, WorkflowStatus
from backend.app.services.llm.base import RuntimeUnavailableError
from backend.app.services.orchestration.workflow import ResearchWorkflow
from backend.app.services.search.base import SearchUnavailableError


def make_plan() -> ResearchPlan:
    return ResearchPlan(
        topic="AI in finance",
        sub_questions=[ResearchSubQuestion(id="q1", question="What are the use cases of AI?")],
        generated_by="deterministic_fallback",
        fallback_reason="llm_unavailable",
    )


def make_source() -> ResearchSource:
    return ResearchSource(
        source_id="src-1",
        title="Research source",
        url="https://example.org/research",
        description="A source snippet supporting the research claim.",
        original_query="What are the use cases of AI?",
    )


class FakePlanner:
    async def create_plan(self, request):
        return make_plan()


class FakeRetrieval:
    def __init__(self, empty: bool = False, fail: bool = False) -> None:
        self.empty = empty
        self.fail = fail
        self.calls = []

    async def retrieve(self, research_id, question, plan):
        self.calls.append(plan.sub_questions[0].question)
        if self.fail:
            raise SearchUnavailableError
        return ResearchRetrievalResponse(
            research_id=UUID(str(research_id)),
            question=question,
            plan=plan,
            status=ResearchStatus.COMPLETED,
            sources=[] if self.empty else [make_source()],
        )


class FakeLLM:
    def __init__(
        self,
        retry: bool = False,
        invalid_analyst: bool = False,
        invalid_verifier: bool = False,
        fail_analysis: bool = False,
        claim_status: str = "supported",
    ) -> None:
        self.retry = retry
        self.invalid_analyst = invalid_analyst
        self.invalid_verifier = invalid_verifier
        self.fail_analysis = fail_analysis
        self.claim_status = claim_status
        self.verification_calls = 0

    async def generate(self, prompt, temperature, max_tokens):
        if prompt.startswith("Analyze only"):
            if self.fail_analysis:
                raise RuntimeUnavailableError
            if self.invalid_analyst:
                return "not JSON", True, 1
            findings = (
                []
                if '"source_id":' not in prompt
                else [
                    {
                        "finding_id": "finding-1",
                        "group": "Use cases",
                        "claim": "AI is used in financial services.",
                        "source_ids": ["src-1"],
                    }
                ]
            )
            return json.dumps({"findings": findings}), True, 1

        self.verification_calls += 1
        if self.invalid_verifier:
            return "not JSON", True, 1
        can_retry = self.retry and self.verification_calls == 1
        claims = []
        if '"finding_id": "finding-1"' in prompt:
            claims = [
                {
                    "finding_id": "finding-1",
                    "status": self.claim_status,
                    "rationale": f"The provided snippet marks this claim {self.claim_status}.",
                    "source_ids": ["src-1"],
                }
            ]
        return (
            json.dumps(
                {
                    "claims": claims,
                    "research_gaps": [],
                    "additional_queries": (["Updated population data"] if can_retry else []),
                    "can_retry": can_retry,
                }
            ),
            True,
            1,
        )


def make_workflow(
    retrieval: FakeRetrieval | None = None,
    llm: FakeLLM | None = None,
) -> tuple[ResearchWorkflow, FakeRetrieval]:
    retrieval = retrieval or FakeRetrieval()
    llm = llm or FakeLLM()
    return ResearchWorkflow(FakePlanner(), retrieval, llm), retrieval


def test_workflow_runs_all_agents_and_returns_inspectable_history():
    workflow, _ = make_workflow()

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.plan is not None
    assert [source.source_id for source in result.sources] == ["src-1"]
    assert result.findings[0].finding_id == "finding-1"
    assert result.report is not None
    assert result.report.sections[0].finding_ids == ["finding-1"]
    assert result.max_retries == 1
    assert result.attempted_queries == ["What are the use cases of AI?"]
    assert result.retrieval_partial is False
    stages = {execution.agent_name for execution in result.execution_history}
    assert {
        WorkflowStage.SUPERVISOR,
        WorkflowStage.PLANNER,
        WorkflowStage.RESEARCHER,
        WorkflowStage.ANALYST,
        WorkflowStage.VERIFIER,
        WorkflowStage.REPORT,
    }.issubset(stages)
    assert all(execution.ended_at >= execution.started_at for execution in result.execution_history)


def test_verifier_routes_one_targeted_research_retry():
    retrieval = FakeRetrieval()
    llm = FakeLLM(retry=True)
    workflow, _ = make_workflow(retrieval, llm)

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.retry_count == 1
    assert len(retrieval.calls) == 2
    assert retrieval.calls[1] == "Updated population data?"
    assert (
        sum(
            execution.agent_name == WorkflowStage.RESEARCHER
            for execution in result.execution_history
        )
        == 2
    )
    assert llm.verification_calls == 2


def test_workflow_sanitizes_and_tracks_agent_failure():
    workflow, _ = make_workflow(
        llm=FakeLLM(invalid_analyst=True),
    )

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[0].stage == WorkflowStage.ANALYST
    assert result.errors[0].code == "invalid_agent_output"
    assert "not JSON" not in result.errors[0].message
    failed = [
        execution
        for execution in result.execution_history
        if execution.agent_name == WorkflowStage.ANALYST
    ]
    assert len(failed) == 1
    assert failed[0].status == "failed"


def test_language_model_failure_is_reported_without_provider_details():
    workflow, _ = make_workflow(llm=FakeLLM(fail_analysis=True))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[0].stage == WorkflowStage.ANALYST
    assert result.errors[0].code == "llm_unavailable"
    assert "runtime" not in result.errors[0].message.lower()


def test_invalid_verifier_output_fails_the_workflow():
    workflow, _ = make_workflow(llm=FakeLLM(invalid_verifier=True))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[0].stage == WorkflowStage.VERIFIER
    assert result.errors[0].code == "invalid_agent_output"


def test_unsupported_claim_is_excluded_from_report_sections():
    workflow, _ = make_workflow(llm=FakeLLM(claim_status="unsupported"))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.report is not None
    assert result.report.sections == []
    assert result.report.research_gaps == ["Unsupported claim: AI is used in financial services."]


def test_search_failure_is_returned_as_failed_workflow_state():
    workflow, _ = make_workflow(retrieval=FakeRetrieval(fail=True))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[0].stage == WorkflowStage.RESEARCHER
    assert result.errors[0].code == "search_unavailable"
    assert result.report is None


def test_no_evidence_produces_partial_report_without_claims():
    workflow, _ = make_workflow(retrieval=FakeRetrieval(empty=True))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.PARTIAL
    assert result.sources == []
    assert result.findings == []
    assert result.report is not None
    assert result.report.sections == []
    assert "No sources were retrieved." in result.report.limitations


def test_each_run_gets_independent_id_and_execution_history():
    workflow, _ = make_workflow()

    first = asyncio.run(workflow.run("How is AI changing finance?", 3))
    second = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert first.research_id != second.research_id
    assert first.execution_history
    assert len(first.execution_history) == len(second.execution_history)
