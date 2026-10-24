"""팀·공고와 현재 집계를 호출자의 세션에서 한 SQL 읽기 시점으로 읽는다."""

from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Select, func, literal, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app.models.contests import Contest, ContestField
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole


class TeamRow(NamedTuple):
    team: Team
    contest: Contest
    member_count: int
    role_codes: Sequence[str]
    field_codes: Sequence[str]


class TeamDetailRow(NamedTuple):
    team: TeamRow
    team_count: int


class TeamListResult(NamedTuple):
    rows: list[TeamRow]
    total: int
    page: int
    contest_exists: bool


def _member_count() -> ScalarSelect[int]:
    return (
        select(func.count())
        .select_from(TeamMembership)
        .where(
            TeamMembership.team_id == Team.team_id, TeamMembership.ended_at.is_(None)
        )
        .correlate(Team)
        .scalar_subquery()
    )


def _role_codes() -> ScalarSelect[list[str] | None]:
    return (
        select(func.array_agg(TeamRecruitmentRole.role_code))
        .where(TeamRecruitmentRole.team_id == Team.team_id)
        .correlate(Team)
        .scalar_subquery()
    )


def _field_codes() -> ScalarSelect[list[str] | None]:
    return (
        select(func.array_agg(ContestField.field_code))
        .where(ContestField.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )


def _detail_statement() -> Select[
    tuple[Team, Contest, int, list[str] | None, list[str] | None, int]
]:
    # 전체 팀 수는 접수 상태·정원 필터와 독립적으로 집계한다.
    team_count = (
        select(func.count())
        .select_from(Team)
        .where(Team.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    return (
        select(
            Team, Contest, _member_count(), _role_codes(), _field_codes(), team_count
        )
        .join(Contest, Contest.contest_id == Team.contest_id)
        .execution_options(populate_existing=True)
    )


async def get_team_detail(session: AsyncSession, team_id: UUID) -> TeamDetailRow | None:
    row = (
        await session.execute(_detail_statement().where(Team.team_id == team_id))
    ).one_or_none()
    if row is None:
        return None
    team, contest, count, roles, fields, team_count = row
    return TeamDetailRow(
        TeamRow(team, contest, count, roles or [], fields or []), team_count
    )


async def list_teams(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    role_code: str | None,
    recruiting_only: bool,
    needle: str,
    matching_roles: Sequence[str],
    contest_id: UUID | None,
    require_contest: bool,
    current: datetime,
) -> TeamListResult:
    members = _member_count()
    matches = select(Team.team_id, Team.created_at).join(
        Contest, Contest.contest_id == Team.contest_id
    )
    if contest_id is not None:
        matches = matches.where(Team.contest_id == contest_id)
    if role_code is not None:
        matches = matches.where(
            select(TeamRecruitmentRole.team_id)
            .where(
                TeamRecruitmentRole.team_id == Team.team_id,
                TeamRecruitmentRole.role_code == role_code,
            )
            .exists()
        )
    if recruiting_only:
        matches = matches.where(
            Team.recruitment_state == "open",
            Contest.registration_opens_at <= current,
            Contest.registration_closes_at > current,
            Team.recruitment_closes_at > current,
            members < Team.target_capacity,
        )
    if needle:
        text_conditions = [
            Team.name.icontains(needle, autoescape=True),
            Team.introduction.icontains(needle, autoescape=True),
            select(TeamRecruitmentRole.team_id)
            .where(
                TeamRecruitmentRole.team_id == Team.team_id,
                TeamRecruitmentRole.role_code.in_(matching_roles),
            )
            .exists(),
        ]
        if not require_contest:
            text_conditions.append(Contest.title.icontains(needle, autoescape=True))
        matches = matches.where(or_(*text_conditions))
    matching = matches.cte("matching_teams")
    stats = select(func.count().label("total")).select_from(matching).cte("team_total")
    last_page = (stats.c.total + page_size - 1) // page_size
    bounded = select(
        stats.c.total,
        func.greatest(1, func.least(page, last_page)).label("page"),
    ).cte("team_page_bounds")
    page_ids = (
        select(matching.c.team_id)
        .order_by(matching.c.created_at.desc(), matching.c.team_id.desc())
        .limit(page_size)
        .offset(select((bounded.c.page - 1) * page_size).scalar_subquery())
        .cte("team_page_ids")
    )
    contest_exists = (
        select(Contest.contest_id).where(Contest.contest_id == contest_id).exists()
        if require_contest
        else literal(True)
    )
    statement = (
        select(
            Team,
            Contest,
            members,
            _role_codes(),
            _field_codes(),
            bounded.c.total,
            bounded.c.page,
            contest_exists,
        )
        .select_from(bounded)
        .outerjoin(page_ids, true())
        .outerjoin(Team, Team.team_id == page_ids.c.team_id)
        .outerjoin(Contest, Contest.contest_id == Team.contest_id)
        .order_by(Team.created_at.desc(), Team.team_id.desc())
        .execution_options(populate_existing=True)
    )
    rows = (await session.execute(statement)).all()
    total, page, found = rows[0][5:]

    items = [
        TeamRow(team, contest, count, roles or [], fields or [])
        for team, contest, count, roles, fields, *_ in rows
        if team is not None
    ]
    return TeamListResult(items, total, page, found)


async def get_team_codes(
    session: AsyncSession, team_id: UUID, contest_id: UUID
) -> tuple[Sequence[str], Sequence[str]]:
    fields = (
        await session.scalars(
            select(ContestField.field_code).where(ContestField.contest_id == contest_id)
        )
    ).all()
    roles = (
        await session.scalars(
            select(TeamRecruitmentRole.role_code).where(
                TeamRecruitmentRole.team_id == team_id
            )
        )
    ).all()
    return fields, roles


async def get_team_contest_id(session: AsyncSession, team_id: UUID) -> UUID | None:
    contest_id: UUID | None = await session.scalar(
        select(Team.contest_id).where(Team.team_id == team_id)
    )
    return contest_id


async def flush(session: AsyncSession) -> None:
    await session.flush()


async def get_application_membership(
    session: AsyncSession, application_id: UUID
) -> TeamMembership | None:
    """지원 시도에 연결된 소속 이력을 같은 업무 세션에서 조회한다."""
    membership: TeamMembership | None = await session.scalar(
        select(TeamMembership).where(
            TeamMembership.source_application_id == application_id
        )
    )
    return membership


async def count_current_members(session: AsyncSession, team_id: UUID) -> int:
    """호출자가 팀 잠금을 유지한 상태에서 현재 소속 인원을 센다."""
    count = await session.scalar(
        select(func.count())
        .select_from(TeamMembership)
        .where(TeamMembership.team_id == team_id, TeamMembership.ended_at.is_(None))
    )
    assert count is not None
    return count
