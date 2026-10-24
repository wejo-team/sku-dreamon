"""DB 연결 검사와 별개로 앱의 기본 HTTP 응답 상태를 제공한다."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
