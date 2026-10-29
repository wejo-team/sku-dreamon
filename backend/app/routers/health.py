"""DB 연결 검사와 별개로 앱의 기본 HTTP 응답 상태를 제공한다."""

from typing import cast

from fastapi import APIRouter, Request, Response

from app.core.config import Settings
from app.core.db.session import Database
from app.schemas.health import HealthResponse
from app.schemas.readiness import ReadinessResponse
from app.security.passwords import PasswordBlocklist
from app.services.health import ReadinessProbe, is_ready

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    available = await is_ready(
        cast(Settings, request.app.state.settings),
        cast(Database | None, getattr(request.app.state, "database", None)),
        cast(
            PasswordBlocklist | None,
            getattr(request.app.state, "password_blocklist", None),
        ),
        getattr(request.app.state, "ai_driver", None),
        cast(ReadinessProbe, request.app.state.readiness_probe),
    )
    response.status_code = 200 if available else 503
    response.headers["Cache-Control"] = "no-store"
    return ReadinessResponse(status="ready" if available else "unavailable")
