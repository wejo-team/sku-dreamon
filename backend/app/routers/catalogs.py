"""인증 없이 조회하는 공통 선택지 API를 제공한다."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, Success
from app.schemas.catalogs import (
    AcademicUnitResponse,
    Catalogs,
    CourseCatalogItem,
    CoursesQuery,
)
from app.services.catalogs import build_catalogs, list_academic_units
from app.services.courses import list_courses

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


@router.get("/courses", summary="과목 검색", responses=error_responses(422))
async def get_courses(
    session: DatabaseSession, query: Annotated[CoursesQuery, Query()]
) -> Page[CourseCatalogItem]:
    return await list_courses(session, query)
