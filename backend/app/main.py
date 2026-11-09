from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.v1 import api_router
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Application startup complete.")
    yield
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
    logger.exception("Unhandled application exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )
