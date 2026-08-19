from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.core.container import AppContainer

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, object]:
    container: AppContainer = request.app.state.container
    errors = await container.readiness_errors()
    if errors:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "failed": errors}
    return {"status": "ready"}

