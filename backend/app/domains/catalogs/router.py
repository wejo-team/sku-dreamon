"""인증 없이 조회하는 공통 선택지 API를 제공한다."""

from fastapi import APIRouter

from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.domains.catalogs.schemas import Catalogs, build_catalogs

router = APIRouter(
    prefix="/catalogs", tags=["catalogs"], responses=error_responses(500, 503)
)


@router.get("", summary="공통 선택지")
async def get_catalogs() -> Success[Catalogs]:
    return Success(data=build_catalogs())
