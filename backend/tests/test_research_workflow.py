import asyncio
import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.schemas.research import (
    QueryRetrievalDiagnostic,
    ResearchPlan,
    ResearchRetrievalResponse,
    ResearchStatus,
    ResearchSubQuestion,
    SearchFailure,
)
from backend.app.schemas.sources import ResearchSource
from backend.app.schemas.workflow import (
    AnalyticalFinding,
    ClaimVerification,
    VerificationResult,
    WorkflowStage,
    WorkflowStatus,
)
from backend.app.services.llm.base import RuntimeUnavailableError
from backend.app.services.orchestration.agents import (
    AgentExecutionError,
    ReportPreparationAgent,
    ResearcherAgent,
)
from backend.app.services.orchestration.workflow import ResearchWorkflow


def make_plan() -> ResearchPlan:
    return ResearchPlan(
        topic="AI in finance",
        sub_questions=[ResearchSubQuestion(id="q1", question="What are the use cases of AI?")],
        generated_by="deterministic_fallback",
        fallback_reason="llm_unavailable",
    )


def make_source(source_id: str = "src-1") -> ResearchSource:
    return ResearchSource(
        source_id=source_id,
        title="Research source",
        url=f"https://example.org/{source_id}",
        description="A source snippet supporting the research claim.",
        original_query="What are the use cases of AI?",
    )


class FakePlanner:
    def __init__(self, delay: float = 0, fail: bool = False) -> None:
        self.delay = delay
        self.fail = fail

    async def create_plan(self, request):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("planner internal details")
        return make_plan()


class FakeRetrieval:
    def __init__(
        self,
        empty: bool = False,
        fail: bool = False,
        delay_by_call: dict[int, float] | None = None,
        multiple_sources: bool = False,
        fail_unexpected: bool = False,
        partial: bool = False,
        fail_calls: set[int] | None = None,
    ) -> None:
        self.empty = empty
        self.fail = fail
        self.delay_by_call = delay_by_call or {}
        self.multiple_sources = multiple_sources
        self.fail_unexpected = fail_unexpected
        self.partial = partial
        self.fail_calls = fail_calls or set()
        self.calls: list[str] = []

    async def retrieve(
        self,
        research_id,
        question,
        plan,
        raise_on_complete_failure=True,
    ):
        self.calls.append(plan.sub_questions[0].question)
        if delay := self.delay_by_call.get(len(self.calls), 0):
            await asyncio.sleep(delay)
        if self.fail_unexpected:
            raise RuntimeError("search internal details")
        if self.fail or len(self.calls) in self.fail_calls:
            query_results = [
                QueryRetrievalDiagnostic(
                    query=subquestion.question,
                    succeeded=False,
                    result_count=0,
                    error_code="search_unavailable",
                    error_message="Search is unavailable.",
                )
                for subquestion in plan.sub_questions
            ]
            return ResearchRetrievalResponse(
                research_id=UUID(str(research_id)),
                question=question,
                plan=plan,
                status=ResearchStatus.FAILED,
                sources=[],
                failures=[
                    SearchFailure(
                        query=item.query,
                        code=item.error_code or "search_unavailable",
                        message=item.error_message or "Search is unavailable.",
                    )
                    for item in query_results
                ],
                query_results=query_results,
            )
        sources = [] if self.empty else [make_source()]
        if self.multiple_sources and not self.empty:
            sources.append(make_source("src-2"))
        return ResearchRetrievalResponse(
            research_id=UUID(str(research_id)),
            question=question,
            plan=plan,
            status=ResearchStatus.PARTIAL if self.partial else ResearchStatus.COMPLETED,
            sources=sources,
            failures=(
                [
                    SearchFailure(
                        query="What supplementary evidence is available?",
                        code="search_timeout",
                        message="The search provider request timed out.",
                    )
                ]
                if self.partial
                else []
            ),
            query_results=[
                QueryRetrievalDiagnostic(
                    query=subquestion.question,
                    succeeded=True,
                    result_count=len(sources),
                )
                for subquestion in plan.sub_questions
            ]
            + (
                [
                    QueryRetrievalDiagnostic(
                        query="What supplementary evidence is available?",
                        succeeded=False,
                        result_count=0,
                        error_code="search_timeout",
                        error_message="The search provider request timed out.",
                    )
                ]
                if self.partial
                else []
            ),
        )


class FakeLLM:
    def __init__(
        self,
        retry: bool = False,
        invalid_analyst: bool = False,
        invalid_verifier: bool = False,
        fail_analysis: bool = False,
        fail_verification: bool = False,
        unexpected_analysis: bool = False,
        delay_analysis: float = 0,
        delay_verification: float = 0,
        claim_status: str = "supported",
        retry_query: str = "Updated population data",
        retry_every_verification: bool = False,
    ) -> None:
        self.retry = retry
        self.invalid_analyst = invalid_analyst
        self.invalid_verifier = invalid_verifier
        self.fail_analysis = fail_analysis
        self.fail_verification = fail_verification
        self.unexpected_analysis = unexpected_analysis
        self.delay_analysis = delay_analysis
        self.delay_verification = delay_verification
        self.claim_status = claim_status
        self.retry_query = retry_query
        self.retry_every_verification = retry_every_verification
        self.verification_calls = 0

    async def generate(self, prompt, temperature, max_tokens):
        if prompt.startswith("Analyze only"):
            if self.delay_analysis:
                await asyncio.sleep(self.delay_analysis)
            if self.fail_analysis:
                raise RuntimeUnavailableError
            if self.unexpected_analysis:
                raise RuntimeError("model internal details")
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
                        "source_ids": (
                            ["src-1", "src-2"] if self.claim_status == "conflicting" else ["src-1"]
                        ),
                    }
                ]
            )
            return json.dumps({"findings": findings}), True, 1

        self.verification_calls += 1
        if self.delay_verification:
            await asyncio.sleep(self.delay_verification)
        if self.fail_verification:
            raise RuntimeError("verifier internal details")
        if self.invalid_verifier:
            return "not JSON", True, 1
        can_retry = self.retry and (self.retry_every_verification or self.verification_calls == 1)
        claims = []
        if '"finding_id": "finding-1"' in prompt:
            claims = [
                {
                    "finding_id": "finding-1",
                    "status": self.claim_status,
                    "rationale": f"The provided snippet marks this claim {self.claim_status}.",
                    "source_ids": (
                        ["src-1", "src-2"] if self.claim_status == "conflicting" else ["src-1"]
                    ),
                }
            ]
        return (
            json.dumps(
                {
                    "claims": claims,
                    "research_gaps": [],
                    "additional_queries": ([self.retry_query] if can_retry else []),
                    "can_retry": can_retry,
                }
            ),
            True,
            1,
        )


def make_workflow(
    retrieval: FakeRetrieval | None = None,
    llm: FakeLLM | None = None,
    planner: FakePlanner | None = None,
    timeout_seconds: float = 300,
    max_retries: int = 1,
) -> tuple[ResearchWorkflow, FakeRetrieval]:
    retrieval = retrieval or FakeRetrieval()
    llm = llm or FakeLLM()
    return (
        ResearchWorkflow(
            planner or FakePlanner(),
            retrieval,
            llm,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        ),
        retrieval,
    )


def test_workflow_runs_all_agents_and_returns_inspectable_history():
    workflow, _ = make_workflow()

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.COMPLETED
    assert result.plan is not None
    assert [source.source_id for source in result.sources] == ["src-1"]
    assert result.findings[0].finding_id == "finding-1"
    assert result.report is not None
    assert result.report.sections[0].finding_ids == ["finding-1"]
    assert result.report.sections[0].finding_sources == {"finding-1": ["src-1"]}
    assert result.max_retries == 1
    assert result.attempted_queries == ["What are the use cases of AI?"]
    assert result.retrieval_partial is False
    assert result.retrieval_diagnostics[0].succeeded is True
    assert result.retrieval_diagnostics[0].result_count == 1
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


@pytest.mark.parametrize(
    ("status", "source_ids", "valid"),
    [
        ("supported", [], False),
        ("partially_supported", [], False),
        ("unsupported", [], True),
        ("conflicting", ["src-1"], False),
        ("conflicting", ["src-1", "src-2"], True),
    ],
)
def test_verification_citation_requirements(status, source_ids, valid):
    values = {
        "finding_id": "finding-1",
        "status": status,
        "rationale": "Evidence assessment.",
        "source_ids": source_ids,
    }

    if valid:
        assert ClaimVerification.model_validate(values).status == status
    else:
        with pytest.raises(ValidationError):
            ClaimVerification.model_validate(values)


def test_source_id_lists_reject_duplicates():
    with pytest.raises(ValidationError, match="unique"):
        AnalyticalFinding(
            finding_id="finding-1",
            group="Evidence",
            claim="A claim",
            source_ids=["src-1", "src-1"],
        )
    with pytest.raises(ValidationError, match="unique"):
        ClaimVerification(
            finding_id="finding-1",
            status="supported",
            rationale="Supported.",
            source_ids=["src-1", "src-1"],
        )


def test_invalid_verification_classification_is_rejected():
    with pytest.raises(ValidationError):
        ClaimVerification(
            finding_id="finding-1",
            status="verified",
            rationale="Not a supported classification.",
            source_ids=["src-1"],
        )


def test_verifier_rejects_unknown_source_ids():
    from backend.app.services.orchestration.agents import VerifierAgent

    verifier = VerifierAgent(FakeLLM())
    with pytest.raises(AgentExecutionError, match="unknown source"):
        asyncio.run(
            verifier.run(
                "How is AI changing finance?",
                [
                    AnalyticalFinding(
                        finding_id="finding-1",
                        group="Evidence",
                        claim="A claim",
                        source_ids=[],
                    )
                ],
                [],
            )
        )


def test_report_preserves_source_refs_and_conflict_evidence():
    finding = AnalyticalFinding(
        finding_id="finding-1",
        group="Evidence",
        claim="A conflicting claim",
        source_ids=["src-1"],
    )
    verification = VerificationResult(
        claims=[
            ClaimVerification(
                finding_id="finding-1",
                status="conflicting",
                rationale="Sources disagree.",
                source_ids=["src-1", "src-2"],
            )
        ]
    )
    report = ReportPreparationAgent().run(
        "Question",
        [finding],
        verification,
        [make_source(), make_source("src-2")],
        False,
    )

    assert report.sections == []
    assert report.conflicts[0].finding_id == "finding-1"
    assert report.conflicts[0].source_ids == ["src-1", "src-2"]


def test_report_keeps_original_and_verifier_source_references():
    finding = AnalyticalFinding(
        finding_id="finding-1",
        group="Evidence",
        claim="A supported claim",
        source_ids=["src-1"],
    )
    verification = VerificationResult(
        claims=[
            ClaimVerification(
                finding_id="finding-1",
                status="supported",
                rationale="Both sources support the claim.",
                source_ids=["src-2"],
            )
        ]
    )
    report = ReportPreparationAgent().run(
        "Question",
        [finding],
        verification,
        [make_source(), make_source("src-2")],
        False,
    )

    assert report.sections[0].finding_sources == {"finding-1": ["src-1", "src-2"]}
    assert report.sections[0].source_ids == ["src-1", "src-2"]


def test_report_rejects_unknown_or_missing_verification_sources():
    finding = AnalyticalFinding(
        finding_id="finding-1",
        group="Evidence",
        claim="A claim",
        source_ids=["src-1"],
    )
    reporter = ReportPreparationAgent()
    verification = VerificationResult(
        claims=[
            ClaimVerification(
                finding_id="finding-1",
                status="supported",
                rationale="Supported.",
                source_ids=["unknown"],
            )
        ]
    )
    with pytest.raises(AgentExecutionError, match="unavailable source"):
        reporter.run("Question", [finding], verification, [make_source()], False)

    with pytest.raises(AgentExecutionError, match="every finding"):
        reporter.run("Question", [finding], VerificationResult(claims=[]), [make_source()], False)


def test_workflow_is_partial_for_partially_supported_claim():
    workflow, _ = make_workflow(llm=FakeLLM(claim_status="partially_supported"))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.PARTIAL
    assert result.report is not None
    assert result.report.sections[0].finding_ids == ["finding-1"]


def test_workflow_is_partial_for_conflicting_claim():
    workflow, _ = make_workflow(
        retrieval=FakeRetrieval(multiple_sources=True),
        llm=FakeLLM(claim_status="conflicting"),
    )

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.PARTIAL
    assert result.report is not None
    assert result.report.conflicts[0].source_ids == ["src-1", "src-2"]


def test_partial_retrieval_keeps_success_and_failure_diagnostics():
    workflow, _ = make_workflow(retrieval=FakeRetrieval(partial=True))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.PARTIAL
    assert [source.source_id for source in result.sources] == ["src-1"]
    assert len(result.retrieval_diagnostics) == 2
    assert result.retrieval_diagnostics[0].succeeded is True
    assert result.retrieval_diagnostics[1].succeeded is False
    assert result.retrieval_diagnostics[1].error_code == "search_timeout"
    assert "timed out" in result.retrieval_diagnostics[1].error_message


def test_failed_targeted_retrieval_keeps_prior_sources_and_finishes_partial():
    retrieval = FakeRetrieval(fail_calls={2})
    workflow, _ = make_workflow(
        retrieval=retrieval,
        llm=FakeLLM(retry=True),
    )

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.PARTIAL
    assert [source.source_id for source in result.sources] == ["src-1"]
    assert result.retrieval_partial is True
    assert len(result.retrieval_diagnostics) == 2
    assert result.retrieval_diagnostics[0].succeeded is True
    assert result.retrieval_diagnostics[1].succeeded is False
    assert result.report is not None


def test_search_failure_is_returned_as_failed_workflow_state():
    workflow, _ = make_workflow(retrieval=FakeRetrieval(fail=True))

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[0].stage == WorkflowStage.RESEARCHER
    assert result.errors[0].code == "search_unavailable"
    assert len(result.retrieval_diagnostics) == 1
    assert result.retrieval_diagnostics[0].error_code == "search_unavailable"
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


@pytest.mark.parametrize(
    ("query", "expected_length", "has_question_mark"),
    [
        ("A useful follow-up query", 25, True),
        ("x" * 499, 500, True),
        ("x" * 500, 500, False),
        (("x" * 499) + ".", 500, False),
    ],
)
def test_targeted_query_construction_respects_final_length(
    query,
    expected_length,
    has_question_mark,
):
    constructed = ResearcherAgent._construct_targeted_question(query)

    assert len(constructed) == expected_length
    assert constructed.endswith("?") is has_question_mark


def test_targeted_query_over_limit_returns_controlled_error():
    with pytest.raises(AgentExecutionError, match="supported length") as error:
        ResearcherAgent._construct_targeted_question("x" * 501)

    assert error.value.code == "invalid_retry_query"


def test_researcher_deduplicates_retry_queries():
    retrieval = FakeRetrieval()
    agent = ResearcherAgent(retrieval)

    _, _, attempted, _, _ = asyncio.run(
        agent.run(
            UUID("00000000-0000-0000-0000-000000000001"),
            "How is AI changing finance?",
            make_plan(),
            [],
            ["New research area", " NEW research area? "],
        )
    )

    assert retrieval.calls == ["New research area?"]
    assert attempted == ["New research area?"]


def test_invalid_retry_request_is_rejected_by_schema():
    with pytest.raises(ValidationError):
        VerificationResult(
            claims=[],
            additional_queries=["A valid follow-up query"],
            can_retry=False,
        )
    with pytest.raises(ValidationError):
        VerificationResult(
            claims=[],
            additional_queries=["x" * 501],
            can_retry=True,
        )


def test_duplicate_retry_query_does_not_run_another_retrieval():
    retrieval = FakeRetrieval()
    workflow, _ = make_workflow(
        retrieval=retrieval,
        llm=FakeLLM(retry=True, retry_query="What are the use cases of AI?"),
    )

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.retry_count == 0
    assert retrieval.calls == ["What are the use cases of AI?"]


def test_retry_is_denied_when_retry_limit_is_zero():
    retrieval = FakeRetrieval()
    workflow, _ = make_workflow(
        retrieval=retrieval,
        llm=FakeLLM(retry=True),
        max_retries=0,
    )

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.retry_count == 0
    assert retrieval.calls == ["What are the use cases of AI?"]


def test_retry_exhaustion_does_not_trigger_a_second_retry():
    retrieval = FakeRetrieval()
    llm = FakeLLM(retry=True, retry_every_verification=True)
    workflow, _ = make_workflow(retrieval=retrieval, llm=llm)

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.retry_count == 1
    assert len(retrieval.calls) == 2
    assert llm.verification_calls == 2


@pytest.mark.parametrize(
    ("planner", "retrieval", "llm", "stage"),
    [
        (FakePlanner(fail=True), FakeRetrieval(), FakeLLM(), WorkflowStage.PLANNER),
        (
            FakePlanner(),
            FakeRetrieval(fail_unexpected=True),
            FakeLLM(),
            WorkflowStage.RESEARCHER,
        ),
        (
            FakePlanner(),
            FakeRetrieval(),
            FakeLLM(unexpected_analysis=True),
            WorkflowStage.ANALYST,
        ),
        (
            FakePlanner(),
            FakeRetrieval(),
            FakeLLM(fail_verification=True),
            WorkflowStage.VERIFIER,
        ),
    ],
)
def test_unexpected_agent_exceptions_are_sanitized(planner, retrieval, llm, stage):
    workflow, _ = make_workflow(planner=planner, retrieval=retrieval, llm=llm)

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[-1].stage == stage
    assert result.errors[-1].code == "internal_agent_error"
    assert "internal details" not in result.errors[-1].message
    assert any(
        execution.agent_name == stage and execution.status == "failed"
        for execution in result.execution_history
    )


def test_report_preparation_exception_is_sanitized():
    workflow, _ = make_workflow()

    class FailingReporter:
        def run(self, **kwargs):
            raise RuntimeError("private report failure details")

    workflow._reporter = FailingReporter()
    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[-1].stage == WorkflowStage.REPORT
    assert result.errors[-1].code == "internal_agent_error"
    assert "private report failure details" not in result.errors[-1].message


def test_workflow_finishes_before_its_deadline():
    workflow, _ = make_workflow(timeout_seconds=2)

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.COMPLETED
    assert not result.errors


def test_workflow_timeout_is_configurable_and_bounded():
    assert Settings(_env_file=None, research_workflow_timeout=45).research_workflow_timeout == 45
    with pytest.raises(ValidationError):
        Settings(_env_file=None, research_workflow_timeout=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, research_workflow_timeout=601)


@pytest.mark.parametrize(
    ("planner", "retrieval", "llm", "stage"),
    [
        (FakePlanner(delay=0.3), FakeRetrieval(), FakeLLM(), WorkflowStage.PLANNER),
        (
            FakePlanner(),
            FakeRetrieval(delay_by_call={1: 0.3}),
            FakeLLM(),
            WorkflowStage.RESEARCHER,
        ),
        (
            FakePlanner(),
            FakeRetrieval(),
            FakeLLM(delay_analysis=0.3),
            WorkflowStage.ANALYST,
        ),
    ],
)
def test_deadline_during_essential_stage_is_terminal(planner, retrieval, llm, stage):
    workflow, _ = make_workflow(
        planner=planner,
        retrieval=retrieval,
        llm=llm,
        timeout_seconds=0.1,
    )

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[-1].code == "workflow_timeout"
    assert result.errors[-1].stage == stage
    assert result.execution_history[-1].agent_name == stage
    assert result.execution_history[-1].status == "failed"
    completed_stages = {execution.agent_name for execution in result.execution_history}
    if stage == WorkflowStage.PLANNER:
        assert WorkflowStage.RESEARCHER not in completed_stages
    elif stage == WorkflowStage.RESEARCHER:
        assert WorkflowStage.ANALYST not in completed_stages
    elif stage == WorkflowStage.ANALYST:
        assert WorkflowStage.VERIFIER not in completed_stages


def test_deadline_during_targeted_retry_preserves_prior_history():
    workflow, retrieval = make_workflow(
        retrieval=FakeRetrieval(delay_by_call={2: 1}),
        llm=FakeLLM(retry=True),
        timeout_seconds=0.2,
    )

    result = asyncio.run(workflow.run("How is AI changing finance?", 3))

    assert result.status == WorkflowStatus.FAILED
    assert result.errors[-1].code == "workflow_timeout"
    assert result.errors[-1].stage == WorkflowStage.RESEARCHER
    assert result.retry_count == 1
    assert len(retrieval.calls) == 2
    assert any(
        item.agent_name == WorkflowStage.VERIFIER and item.status == "succeeded"
        for item in result.execution_history
    )
    assert result.execution_history[-1].status == "failed"


def test_overlapping_runs_keep_ids_state_and_sources_independent():
    class PerRequestPlanner:
        async def create_plan(self, request):
            return ResearchPlan(
                topic=request.question,
                sub_questions=[
                    ResearchSubQuestion(
                        id="q1",
                        question="What evidence addresses this request?",
                    )
                ],
                generated_by="deterministic_fallback",
                fallback_reason="llm_unavailable",
            )

    class BarrierRetrieval:
        def __init__(self):
            self.started = 0
            self.both_started = asyncio.Event()

        async def retrieve(self, research_id, question, plan, raise_on_complete_failure=True):
            self.started += 1
            if self.started == 2:
                self.both_started.set()
            await self.both_started.wait()
            source_id = f"src-{research_id.hex[:12]}"
            source = ResearchSource(
                source_id=source_id,
                title=question,
                url=f"https://example.org/{research_id}",
                description=f"Evidence for {question}",
                original_query=plan.sub_questions[0].question,
            )
            return ResearchRetrievalResponse(
                research_id=research_id,
                question=question,
                plan=plan,
                status=ResearchStatus.COMPLETED,
                sources=[source],
                query_results=[
                    QueryRetrievalDiagnostic(
                        query=plan.sub_questions[0].question,
                        succeeded=True,
                        result_count=1,
                    )
                ],
            )

    class EchoLLM:
        async def generate(self, prompt, temperature, max_tokens):
            if prompt.startswith("Analyze only"):
                evidence = json.loads(prompt.split("Evidence: ", 1)[1])
                source_id = evidence[0]["source_id"]
                output = {
                    "findings": [
                        {
                            "finding_id": f"f-{source_id}",
                            "group": "Evidence",
                            "claim": f"Claim for {source_id}",
                            "source_ids": [source_id],
                        }
                    ]
                }
            else:
                claims_text = prompt.split("Claims: ", 1)[1].split("\nEvidence:", 1)[0]
                claims = json.loads(claims_text)
                output = {
                    "claims": [
                        {
                            "finding_id": claim["finding_id"],
                            "status": "supported",
                            "rationale": "The supplied evidence supports the claim.",
                            "source_ids": claim["source_ids"],
                        }
                        for claim in claims
                    ],
                    "research_gaps": [],
                    "additional_queries": [],
                    "can_retry": False,
                }
            return json.dumps(output), True, 1

    async def run_two(workflow):
        return await asyncio.gather(
            workflow.run("How does climate research progress?", 1),
            workflow.run("How does finance research progress?", 1),
        )

    retrieval = BarrierRetrieval()
    workflow = ResearchWorkflow(PerRequestPlanner(), retrieval, EchoLLM())
    first, second = asyncio.run(run_two(workflow))

    assert first.research_id != second.research_id
    first_source_ids = {source.source_id for source in first.sources}
    second_source_ids = {source.source_id for source in second.sources}
    assert first_source_ids.isdisjoint(second_source_ids)
    assert first.findings[0].source_ids == list(first_source_ids)
    assert second.findings[0].source_ids == list(second_source_ids)
    assert first.execution_history is not second.execution_history
