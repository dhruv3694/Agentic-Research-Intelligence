from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.api.v1 import api_router
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.schemas.llm import APIError, APIErrorDetail
from backend.app.services.llm.base import LLMProviderError
from backend.app.services.llm.manager import LLMManager
from backend.app.services.llm.ollama_provider import OllamaProvider
from backend.app.services.research.planner import ResearchPlanner
from backend.app.services.research.retrieval import ResearchRetrievalService
from backend.app.services.research.source_processor import SourceProcessor
from backend.app.services.search.base import (
    DisabledSearchProvider,
    SearchProviderError,
)
from backend.app.services.search.providers.searxng import SearXNGSearchProvider

logger = get_logger(__name__)


def create_ollama_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.ollama_base_url,
        timeout=httpx.Timeout(settings.ollama_timeout),
    )


def create_searxng_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.searxng_base_url,
        timeout=httpx.Timeout(settings.search_timeout),
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    http_client = create_ollama_http_client()
    provider = OllamaProvider(
        client=http_client,
        model=settings.ollama_model,
        temperature=settings.ollama_temperature,
        num_ctx=settings.ollama_num_ctx,
    )
    application.state.llm_manager = LLMManager(provider, settings.ollama_model)
    application.state.research_planner = ResearchPlanner(
        provider,
        settings.research_max_subquestions,
    )
    search_client: httpx.AsyncClient | None = None
    if settings.search_provider == "searxng":
        search_client = create_searxng_http_client()
        search_provider = SearXNGSearchProvider(search_client, settings.search_max_results)
    else:
        search_provider = DisabledSearchProvider()
    application.state.search_provider = search_provider
    application.state.research_retrieval_service = ResearchRetrievalService(
        search_provider=search_provider,
        source_processor=SourceProcessor(),
        max_results=settings.search_max_results,
        max_concurrent_searches=settings.research_max_concurrent_searches,
    )
    logger.info("Application startup complete.")
    try:
        yield
    finally:
        if search_client is not None:
            await search_client.aclose()
        await http_client.aclose()
        logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Agentic Research Intelligence backend API.",
    debug=settings.debug,
    lifespan=lifespan,
)


@app.get("/", tags=["Root"], summary="API status")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled application exception (%s).", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content=APIError(
            error=APIErrorDetail(
                code="internal_server_error",
                message="An unexpected server error occurred.",
            )
        ).model_dump(),
    )


@app.exception_handler(LLMProviderError)
async def llm_provider_exception_handler(_: Request, exc: LLMProviderError) -> JSONResponse:
    logger.warning("Language model provider error (%s).", exc.code)
    return JSONResponse(
        status_code=exc.status_code,
        content=APIError(
            error=APIErrorDetail(code=exc.code, message=exc.public_message)
        ).model_dump(),
    )


@app.exception_handler(SearchProviderError)
async def search_provider_exception_handler(
    _: Request,
    exc: SearchProviderError,
) -> JSONResponse:
    logger.warning("Search provider error (%s).", exc.code)
    return JSONResponse(
        status_code=exc.status_code,
        content=APIError(
            error=APIErrorDetail(code=exc.code, message=exc.public_message)
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=APIError(
            error=APIErrorDetail(
                code="validation_error",
                message="The request contains invalid or out-of-range values.",
            )
        ).model_dump(),
    )
