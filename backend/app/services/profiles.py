"""본인·공개 프로필 조회의 권한과 요청 단위 스냅샷을 관리한다."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.queries import profiles as queries
from app.schemas.profiles import PeopleQuery, PersonSummary, ProfileResponse


async def _start_snapshot(session: AsyncSession) -> None:
    # 인증은 별도 세션에서 끝나며, 이 읽기 서비스가 요청 DB의 첫 접근을 소유한다.
    if session.in_transaction():
        raise RuntimeError(
            "Profile reads require a session without an active transaction"
        )
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


async def get_own_profile(session: AsyncSession, account_id: UUID) -> ProfileResponse:
    """인증된 본인에게 비공개를 포함한 현재 프로필을 반환한다."""
    await _start_snapshot(session)
    profile = await queries.get_profile(session, account_id)
    if profile is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    return await queries.build_profile_response(session, profile)


async def get_public_profile(
    session: AsyncSession, account_id: UUID
) -> ProfileResponse:
    """일반 상세에서는 본인·팀장 여부와 관계없이 공개된 프로필만 반환한다."""
    await _start_snapshot(session)
    profile = await queries.get_profile(session, account_id, public_only=True)
    if profile is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
    return await queries.build_profile_response(session, profile)


async def list_people(session: AsyncSession, query: PeopleQuery) -> Page[PersonSummary]:
    """공개 검색 결과와 집계를 같은 스냅샷에서 읽고 마지막 페이지로 보정한다."""
    await _start_snapshot(session)
    total = await queries.count_people(session, query)
    total_pages = (total + query.page_size - 1) // query.page_size
    page = min(query.page, max(total_pages, 1))
    summaries = await queries.list_people_summaries(session, query, page=page)
    return Page(
        data=summaries,
        pagination=PageMeta(
            page=page, page_size=query.page_size, total=total, total_pages=total_pages
        ),
    )
