import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph

from backend.app.schemas.workflow import (
    AgentExecution,
    ResearchWorkflowRunResponse,
    ResearchWorkflowState,
    WorkflowError,
    WorkflowStage,
    WorkflowStatus,
)
from backend.app.services.llm.base import LLMProvider
from backend.app.services.orchestration.agents import (
    AgentExecutionError,
    AnalystAgent,
    PlannerAgent,
    ReportPreparationAgent,
    ResearcherAgent,
    VerifierAgent,
)
from backend.app.services.research.planner import ResearchPlanner
from backend.app.services.research.retrieval import ResearchRetrievalService
from backend.app.services.search.base import SearchProviderError

logger = logging.getLogger(__name__)

AgentNode = Callable[[ResearchWorkflowState], Awaitable[dict[str, Any]]]


class SupervisorAgent:
    """Deterministic supervisor with explicit and bounded routing decisions."""

    def route(self, state: ResearchWorkflowState) -> WorkflowStage:
        if state.get("status") == WorkflowStatus.FAILED:
            return WorkflowStage.END
        requested = state.get("next_stage", WorkflowStage.END)
        if (
            requested != WorkflowStage.RESEARCHER
            or state.get("current_stage") != WorkflowStage.VERIFIER
        ):
            return requested

        verification = state.get("verification")
        if (
            verification is None
            or not verification.can_retry
            or state.get("retry_count", 0) >= state.get("max_retries", 0)
        ):
            return WorkflowStage.REPORT

        attempted = {query.casefold().strip(" ?!.") for query in state.get("attempted_queries", [])}
        new_queries = [
            query
            for query in verification.additional_queries
            if query.casefold().strip(" ?!.") not in attempted
        ]
        return WorkflowStage.RESEARCHER if new_queries else WorkflowStage.REPORT


class ResearchWorkflow:
    def __init__(
        self,
        planner: ResearchPlanner,
        retrieval: ResearchRetrievalService,
        llm: LLMProvider,
        max_retries: int = 1,
    ) -> None:
        if not 0 <= max_retries <= 1:
            raise ValueError("max_retries must be between 0 and 1")
        self._planner = PlannerAgent(planner)
        self._researcher = ResearcherAgent(retrieval)
        self._analyst = AnalystAgent(llm)
        self._verifier = VerifierAgent(llm)
        self._reporter = ReportPreparationAgent()
        self._supervisor = SupervisorAgent()
        self._max_retries = max_retries
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(ResearchWorkflowState)
        builder.add_node("supervisor", self._supervisor_node)
        builder.add_node("planner", self._planner_node)
        builder.add_node("researcher", self._researcher_node)
        builder.add_node("analyst", self._analyst_node)
        builder.add_node("verifier", self._verifier_node)
        builder.add_node("report_preparation", self._report_node)

        builder.add_edge(START, "supervisor")
        for node in (
            "planner",
            "researcher",
            "analyst",
            "verifier",
            "report_preparation",
        ):
            builder.add_edge(node, "supervisor")
        builder.add_conditional_edges(
            "supervisor",
            self._route,
            {
                WorkflowStage.PLANNER: "planner",
                WorkflowStage.RESEARCHER: "researcher",
                WorkflowStage.ANALYST: "analyst",
                WorkflowStage.VERIFIER: "verifier",
                WorkflowStage.REPORT: "report_preparation",
                WorkflowStage.END: END,
            },
        )
        return builder.compile()

    @staticmethod
    def _route(state: ResearchWorkflowState) -> WorkflowStage:
        return state.get("next_stage", WorkflowStage.END)

    async def run(self, question: str, max_subquestions: int) -> ResearchWorkflowRunResponse:
        research_id = uuid4()
        started_at = datetime.now(UTC)
        initial_state: ResearchWorkflowState = {
            "research_id": str(research_id),
            "question": question,
            "max_subquestions": max_subquestions,
            "plan": None,
            "sources": [],
            "findings": [],
            "verification": None,
            "report": None,
            "current_stage": WorkflowStage.SUPERVISOR,
            "next_stage": WorkflowStage.PLANNER,
            "execution_history": [],
            "errors": [],
            "retrieval_partial": False,
            "attempted_queries": [],
            "targeted_queries": [],
            "retry_count": 0,
            "max_retries": self._max_retries,
            "status": WorkflowStatus.RUNNING,
            "started_at": started_at,
            "completed_at": None,
        }
        final_state = await self.graph.ainvoke(
            initial_state,
            {"recursion_limit": 32},
        )
        completed_at = final_state.get("completed_at") or datetime.now(UTC)
        final_state["completed_at"] = completed_at
        return ResearchWorkflowRunResponse(
            research_id=research_id,
            question=question,
            status=final_state["status"],
            plan=final_state.get("plan"),
            sources=final_state.get("sources", []),
            findings=final_state.get("findings", []),
            verification=final_state.get("verification"),
            report=final_state.get("report"),
            execution_history=final_state.get("execution_history", []),
            retry_count=final_state.get("retry_count", 0),
            max_retries=final_state.get("max_retries", self._max_retries),
            attempted_queries=final_state.get("attempted_queries", []),
            retrieval_partial=final_state.get("retrieval_partial", False),
            started_at=started_at,
            completed_at=completed_at,
            errors=final_state.get("errors", []),
        )

    async def _supervisor_node(self, state: ResearchWorkflowState) -> dict[str, Any]:
        started = datetime.now(UTC)
        timer = perf_counter()
        target = self._supervisor.route(state)
        retry_count = state.get("retry_count", 0)
        if (
            state.get("current_stage") == WorkflowStage.VERIFIER
            and target == WorkflowStage.RESEARCHER
        ):
            retry_count += 1
        status = state.get("status", WorkflowStatus.RUNNING)
        if target == WorkflowStage.END and status != WorkflowStatus.FAILED:
            verification = state.get("verification")
            has_unresolved = bool(
                state.get("retrieval_partial")
                or not state.get("sources")
                or (
                    verification
                    and (
                        verification.research_gaps
                        or any(
                            claim.status in {"unsupported", "conflicting"}
                            for claim in verification.claims
                        )
                    )
                )
            )
            status = WorkflowStatus.PARTIAL if has_unresolved else WorkflowStatus.COMPLETED
        ended = datetime.now(UTC)
        execution = AgentExecution(
            agent_name=WorkflowStage.SUPERVISOR,
            started_at=started,
            ended_at=ended,
            status="succeeded",
            duration_ms=round((perf_counter() - timer) * 1000),
            retry_count=retry_count,
        )
        return {
            "current_stage": WorkflowStage.SUPERVISOR,
            "next_stage": target,
            "retry_count": retry_count,
            "status": status,
            "completed_at": ended if target == WorkflowStage.END else None,
            "execution_history": state.get("execution_history", []) + [execution],
        }

    async def _planner_node(self, state: ResearchWorkflowState) -> dict[str, Any]:
        async def execute() -> dict[str, Any]:
            plan = await self._planner.run(
                state["question"],
                state["max_subquestions"],
            )
            return {
                "plan": plan,
                "next_stage": WorkflowStage.RESEARCHER,
                "attempted_queries": [question.question for question in plan.sub_questions],
                "targeted_queries": [],
            }

        return await self._execute_agent(state, WorkflowStage.PLANNER, execute)

    async def _researcher_node(self, state: ResearchWorkflowState) -> dict[str, Any]:
        async def execute() -> dict[str, Any]:
            plan = state["plan"]
            if plan is None:
                raise AgentExecutionError("missing_plan", "The research plan is unavailable.")
            targets = state.get("targeted_queries", [])
            sources, partial, attempted = await self._researcher.run(
                research_id=UUID(state["research_id"]),
                question=state["question"],
                plan=plan,
                previous_sources=state.get("sources", []),
                targeted_queries=targets if targets else None,
            )
            known_queries = set(state.get("attempted_queries", []))
            return {
                "sources": sources,
                "retrieval_partial": state.get("retrieval_partial", False) or partial,
                "attempted_queries": list(dict.fromkeys([*known_queries, *attempted])),
                "targeted_queries": [],
                "next_stage": WorkflowStage.ANALYST,
            }

        return await self._execute_agent(state, WorkflowStage.RESEARCHER, execute)

    async def _analyst_node(self, state: ResearchWorkflowState) -> dict[str, Any]:
        async def execute() -> dict[str, Any]:
            findings = await self._analyst.run(
                state["question"],
                state.get("sources", []),
            )
            return {"findings": findings, "next_stage": WorkflowStage.VERIFIER}

        return await self._execute_agent(state, WorkflowStage.ANALYST, execute)

    async def _verifier_node(self, state: ResearchWorkflowState) -> dict[str, Any]:
        async def execute() -> dict[str, Any]:
            verification = await self._verifier.run(
                state["question"],
                state.get("findings", []),
                state.get("sources", []),
            )
            may_retry = verification.can_retry and state.get("retry_count", 0) < state.get(
                "max_retries", 0
            )
            attempted = {
                query.casefold().strip(" ?!.") for query in state.get("attempted_queries", [])
            }
            targets = [
                query
                for query in verification.additional_queries
                if query.casefold().strip(" ?!.") not in attempted
            ]
            if not targets:
                may_retry = False
            return {
                "verification": verification,
                "targeted_queries": targets if may_retry else [],
                "next_stage": (WorkflowStage.RESEARCHER if may_retry else WorkflowStage.REPORT),
            }

        return await self._execute_agent(state, WorkflowStage.VERIFIER, execute)

    async def _report_node(self, state: ResearchWorkflowState) -> dict[str, Any]:
        async def execute() -> dict[str, Any]:
            verification = state.get("verification")
            if verification is None:
                raise AgentExecutionError(
                    "missing_verification",
                    "Research verification is unavailable.",
                )
            report = self._reporter.run(
                question=state["question"],
                findings=state.get("findings", []),
                verification=verification,
                sources=state.get("sources", []),
                retrieval_partial=state.get("retrieval_partial", False),
            )
            return {"report": report, "next_stage": WorkflowStage.END}

        return await self._execute_agent(state, WorkflowStage.REPORT, execute)

    async def _execute_agent(
        self,
        state: ResearchWorkflowState,
        stage: WorkflowStage,
        action: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        timer = perf_counter()
        try:
            result = await action()
        except (AgentExecutionError, SearchProviderError) as exc:
            code = exc.code
            message = getattr(exc, "public_message", "A workflow agent could not complete.")
            logger.warning("Research workflow stage failed (%s, %s).", stage.value, code)
            ended_at = datetime.now(UTC)
            record = AgentExecution(
                agent_name=stage,
                started_at=started_at,
                ended_at=ended_at,
                status="failed",
                duration_ms=round((perf_counter() - timer) * 1000),
                retry_count=state.get("retry_count", 0),
                error_code=code,
            )
            return {
                "current_stage": stage,
                "next_stage": WorkflowStage.END,
                "status": WorkflowStatus.FAILED,
                "completed_at": ended_at,
                "errors": state.get("errors", [])
                + [WorkflowError(stage=stage, code=code, message=message)],
                "execution_history": state.get("execution_history", []) + [record],
            }
        except Exception as exc:
            logger.error(
                "Unexpected research workflow stage failure (%s, %s).",
                stage.value,
                type(exc).__name__,
            )
            ended_at = datetime.now(UTC)
            record = AgentExecution(
                agent_name=stage,
                started_at=started_at,
                ended_at=ended_at,
                status="failed",
                duration_ms=round((perf_counter() - timer) * 1000),
                retry_count=state.get("retry_count", 0),
                error_code="internal_agent_error",
            )
            return {
                "current_stage": stage,
                "next_stage": WorkflowStage.END,
                "status": WorkflowStatus.FAILED,
                "completed_at": ended_at,
                "errors": state.get("errors", [])
                + [
                    WorkflowError(
                        stage=stage,
                        code="internal_agent_error",
                        message="An internal workflow stage failed.",
                    )
                ],
                "execution_history": state.get("execution_history", []) + [record],
            }

        ended_at = datetime.now(UTC)
        record = AgentExecution(
            agent_name=stage,
            started_at=started_at,
            ended_at=ended_at,
            status="succeeded",
            duration_ms=round((perf_counter() - timer) * 1000),
            retry_count=state.get("retry_count", 0),
        )
        return {
            **result,
            "current_stage": stage,
            "execution_history": state.get("execution_history", []) + [record],
        }
