"""인증 없이 조회하는 공통 선택지 API를 제공한다."""

from fastapi import APIRouter

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.schemas.catalogs import AcademicUnitResponse, Catalogs
from app.services.catalogs import build_catalogs, list_academic_units

router = APIRouter(
    prefix="/catalogs", tags=["catalogs"], responses=error_responses(500, 503)
)


@router.get("", summary="공통 선택지")
async def get_catalogs() -> Success[Catalogs]:
    return Success(data=build_catalogs())


@router.get("/academic-units", summary="학사 소속 목록")
async def get_academic_units(
    session: DatabaseSession,
) -> Success[list[AcademicUnitResponse]]:
    return Success(data=await list_academic_units(session))
