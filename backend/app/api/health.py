from fastapi import APIRouter, HTTPException, status

from app.services import health as health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.head("", include_in_schema=False)
@router.get("")
async def health() -> dict[str, str]:
    """Liveness: the process is up. Touches nothing else."""
    return {"status": "ok"}


@router.head("/ready", include_in_schema=False)
@router.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness: the database answers SELECT 1 through the app role."""
    if not await health_service.database_ready():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="not ready")
    return {"status": "ready"}
