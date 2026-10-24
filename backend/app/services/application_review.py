"""받은 팀장의 현재 지원자 조회와 명시적 검토 행동을 처리한다."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.schemas import Page
from app.queries import applications as application_queries
from app.schemas.application_review import ApplicantResponse, ApplicantSearch


async def _read_snapshot(session: AsyncSession) -> None:
    if session.in_transaction():
        raise RuntimeError("Applicant reads require a fresh request session")
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


async def list_applicants(
    session: AsyncSession, team_id: UUID, account_id: UUID, query: ApplicantSearch
) -> Page[ApplicantResponse]:
    await _read_snapshot(session)
    return await application_queries.list_applicants(
        session, team_id, account_id, query
    )


async def get_applicant(
    session: AsyncSession, application_id: UUID, account_id: UUID
) -> ApplicantResponse:
    await _read_snapshot(session)
    return await application_queries.get_applicant(session, application_id, account_id)
