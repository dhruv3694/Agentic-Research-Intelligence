from fastapi import APIRouter, status

from backend.app.core.config import settings

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, object]:
    return {
        "status": "ok",
        "application": {
            "name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env,
        },
        "message": "Service is healthy.",
    }
