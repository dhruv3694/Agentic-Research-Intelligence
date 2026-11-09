from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from backend.app.schemas.llm import APIError
from backend.app.schemas.research import (
    ResearchPlanResponse,
    ResearchRequest,
    ResearchRetrievalRequest,
    ResearchRetrievalResponse,
    ResearchStatus,
)
from backend.app.schemas.workflow import ResearchWorkflowRunResponse
from backend.app.services.orchestration.workflow import ResearchWorkflow
from backend.app.services.research.planner import ResearchPlanner
from backend.app.services.research.retrieval import ResearchRetrievalService

router = APIRouter(prefix="/research")


def get_research_planner(request: Request) -> ResearchPlanner:
    return request.app.state.research_planner


def get_retrieval_service(request: Request) -> ResearchRetrievalService:
    return request.app.state.research_retrieval_service


def get_research_workflow(request: Request) -> ResearchWorkflow:
    return request.app.state.research_workflow


@router.post(
    "/plan",
    response_model=ResearchPlanResponse,
    responses={422: {"model": APIError}},
)
async def create_research_plan(
    request: ResearchRequest,
    planner: Annotated[ResearchPlanner, Depends(get_research_planner)],
) -> ResearchPlanResponse:
    plan = await planner.create_plan(request)
    return ResearchPlanResponse(
        research_id=uuid4(),
        question=request.question,
        plan=plan,
        status=ResearchStatus.PLANNED,
    )


@router.post(
    "/retrieve",
    response_model=ResearchRetrievalResponse,
    responses={
        422: {"model": APIError},
        502: {"model": APIError},
        503: {"model": APIError},
        504: {"model": APIError},
    },
)
async def retrieve_research_sources(
    request: ResearchRetrievalRequest,
    retrieval_service: Annotated[
        ResearchRetrievalService,
        Depends(get_retrieval_service),
    ],
) -> ResearchRetrievalResponse:
    return await retrieval_service.retrieve(
        research_id=request.research_id,
        question=request.question,
        plan=request.plan,
    )


@router.post(
    "/run",
    response_model=ResearchWorkflowRunResponse,
    responses={422: {"model": APIError}},
)
async def run_research_workflow(
    request: ResearchRequest,
    workflow: Annotated[ResearchWorkflow, Depends(get_research_workflow)],
) -> ResearchWorkflowRunResponse:
    return await workflow.run(request.question, request.max_subquestions)
