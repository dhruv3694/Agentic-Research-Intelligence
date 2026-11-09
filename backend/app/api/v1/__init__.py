from fastapi import APIRouter

from backend.app.api.v1.endpoints.health import router as health_router
from backend.app.api.v1.endpoints.llm import router as llm_router
from backend.app.api.v1.endpoints.research import router as research_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="", tags=["Health"])
api_router.include_router(llm_router, tags=["LLM"])
api_router.include_router(research_router, tags=["Research"])

__all__ = ["api_router"]
