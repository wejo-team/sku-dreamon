"""공유 AI 실행의 조회·정리와 전송 중 변경을 막는 짧은 행 잠금을 제공한다."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_runs import AiRun
from app.models.applications import Application
from app.models.auth import Account, AuthSession
from app.models.contests import Contest
from app.models.profiles import Profile
from app.models.teams import Team, TeamMembership


async def get_run(
    session: AsyncSession, request_id: UUID, *, lock: bool = False
) -> AiRun | None:
    statement = (
        select(AiRun)
        .where(AiRun.ai_run_id == request_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        statement = statement.with_for_update()
    return (await session.scalars(statement)).one_or_none()


async def find_message(
    session: AsyncSession,
    auth_session_id: UUID,
    conversation_id: UUID,
    client_message_id: UUID,
) -> AiRun | None:
    return (
        await session.scalars(
            select(AiRun).where(
                AiRun.auth_session_id == auth_session_id,
                AiRun.conversation_id == conversation_id,
                AiRun.client_message_id == client_message_id,
            )
        )
    ).one_or_none()


async def pending_count(
    session: AsyncSession, account_id: UUID, scope_key: str | None = None
) -> int:
    statement = (
        select(func.count())
        .select_from(AiRun)
        .where(AiRun.account_id == account_id, AiRun.status == "pending")
    )
    if scope_key is not None:
        statement = statement.where(AiRun.scope_key == scope_key)
    return int(await session.scalar(statement) or 0)


async def recent_count(session: AsyncSession, account_id: UUID, since: datetime) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(AiRun.attempt), 0))
            .select_from(AiRun)
            .where(AiRun.account_id == account_id, AiRun.updated_at >= since)
        )
        or 0
    )


async def expire_runs(session: AsyncSession, now: datetime) -> None:
    await session.execute(
        update(AiRun)
        .where(AiRun.status == "pending", AiRun.deadline_at <= now)
        .values(status="failed", failure_code="temporary_failure", updated_at=now)
    )
    await session.execute(delete(AiRun).where(AiRun.expires_at <= now))


def add_run(session: AsyncSession, run: AiRun) -> None:
    session.add(run)


async def flush(session: AsyncSession) -> None:
    await session.flush()


async def session_record(
    session: AsyncSession, auth_session_id: UUID, *, lock: bool = False
) -> AuthSession | None:
    query = (
        select(AuthSession)
        .where(AuthSession.auth_session_id == auth_session_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update(read=True)
    return (await session.scalars(query)).one_or_none()


async def lock_publication_sources(
    session: AsyncSession,
    *,
    account_ids: Sequence[UUID],
    contest_ids: Sequence[UUID],
    team_ids: Sequence[UUID],
    application_ids: Sequence[UUID],
    profile_ids: Sequence[UUID],
) -> None:
    """업무 변경과 같은 계정→공고→팀→지원 순서로 SHARE 잠금을 획득한다."""
    for column, identifiers in (
        (Account.account_id, account_ids),
        (Contest.contest_id, contest_ids),
        (Team.team_id, team_ids),
        (Application.application_id, application_ids),
        (Profile.profile_id, profile_ids),
    ):
        if identifiers:
            await session.execute(
                select(column)
                .where(column.in_(identifiers))
                .order_by(column)
                .with_for_update(read=True)
            )


async def can_recommend_team(
    session: AsyncSession, team_id: UUID, contest_id: UUID, account_id: UUID
) -> bool:
    membership = await session.scalar(
        select(TeamMembership.team_membership_id)
        .where(
            TeamMembership.account_id == account_id,
            TeamMembership.contest_id == contest_id,
            TeamMembership.ended_at.is_(None),
        )
        .limit(1)
    )
    blocked = await session.scalar(
        select(Application.application_id)
        .where(
            Application.team_id == team_id,
            Application.applicant_account_id == account_id,
            Application.status.in_(["submitted", "reviewing", "selected", "rejected"]),
        )
        .limit(1)
    )
    return membership is None and blocked is None
