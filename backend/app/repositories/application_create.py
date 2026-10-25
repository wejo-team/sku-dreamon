"""지원 생성의 재전송·중복·미선발 이력 조회와 신규 행 저장을 담당한다."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.applications import Application
from app.models.teams import Team


async def find_request(
    session: AsyncSession, account_id: UUID, request_id: UUID
) -> Application | None:
    row: Application | None = await session.scalar(
        select(Application)
        .where(
            Application.applicant_account_id == account_id,
            Application.request_id == request_id,
        )
        .execution_options(populate_existing=True)
    )
    return row


async def get_team_contest(session: AsyncSession, team_id: UUID) -> UUID | None:
    contest_id: UUID | None = await session.scalar(
        select(Team.contest_id).where(Team.team_id == team_id)
    )
    return contest_id


async def has_history(
    session: AsyncSession, account_id: UUID, team_id: UUID, statuses: tuple[str, ...]
) -> bool:
    exists = await session.scalar(
        select(
            select(Application.application_id)
            .where(
                Application.applicant_account_id == account_id,
                Application.team_id == team_id,
                Application.status.in_(statuses),
            )
            .exists()
        )
    )
    assert exists is not None
    return exists


async def insert_application(session: AsyncSession, application: Application) -> None:
    session.add(application)
    await session.flush()
