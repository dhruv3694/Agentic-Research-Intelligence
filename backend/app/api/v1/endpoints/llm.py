from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from backend.app.schemas.llm import (
    APIError,
    GenerateRequest,
    GenerateResponse,
    LLMStatusResponse,
    ModelsResponse,
)
from backend.app.services.llm.manager import LLMManager

router = APIRouter(prefix="/llm")


def get_llm_manager(request: Request) -> LLMManager:
    return request.app.state.llm_manager


@router.get(
    "/status",
    response_model=LLMStatusResponse,
)
async def llm_status(
    manager: Annotated[LLMManager, Depends(get_llm_manager)],
) -> LLMStatusResponse:
    return LLMStatusResponse.model_validate(await manager.status())


@router.get(
    "/models",
    response_model=ModelsResponse,
    responses={
        502: {"model": APIError},
        503: {"model": APIError},
        504: {"model": APIError},
    },
)
async def list_models(
    manager: Annotated[LLMManager, Depends(get_llm_manager)],
) -> ModelsResponse:
    return ModelsResponse(models=await manager.list_models())


@router.post(
    "/generate",
    response_model=GenerateResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": APIError},
        422: {"model": APIError},
        502: {"model": APIError},
        503: {"model": APIError},
        504: {"model": APIError},
    },
)
async def generate(
    request: GenerateRequest,
    manager: Annotated[LLMManager, Depends(get_llm_manager)],
) -> GenerateResponse:
    return GenerateResponse.model_validate(
        await manager.generate(request.prompt, request.temperature, request.max_tokens)
    )
