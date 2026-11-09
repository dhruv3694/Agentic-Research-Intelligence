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

logger = get_logger(__name__)


def create_ollama_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.ollama_base_url,
        timeout=httpx.Timeout(settings.ollama_timeout),
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
    logger.info("Application startup complete.")
    try:
        yield
    finally:
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
