"""공개 팀과 현재 집계를 한 SQL 읽기 시점에서 조회한다."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, literal, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.domains.catalogs.codes import RoleCode
from app.domains.contests.models import Contest, ContestField
from app.domains.contests.schemas import build_contest_summary
from app.domains.teams.models import Team, TeamMembership, TeamRecruitmentRole
from app.domains.teams.schemas import (
    TeamDetail,
    TeamSearch,
    TeamSummary,
    build_team_summary,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


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


async def get_team_detail(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> TeamDetail:
    """호출자의 트랜잭션을 유지하며 공개 필드와 전체 팀 수를 함께 읽는다."""
    current = _utcnow() if now is None else now
    row = (
        await session.execute(_detail_statement().where(Team.team_id == team_id))
    ).one_or_none()
    if row is None:
        raise AppError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다.")
    team, contest, count, roles, fields, team_count = row
    summary = build_team_summary(
        team,
        contest,
        field_codes=fields or [],
        role_codes=roles or [],
        member_count=count,
        now=current,
    )
    return TeamDetail(
        **summary.model_dump(by_alias=False),
        owner_account_id=team.leader_account_id,
        contest=build_contest_summary(
            contest, field_codes=fields or [], team_count=team_count, now=current
        ),
    )


async def get_team_summary(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> TeamSummary:
    detail = await get_team_detail(session, team_id, now=now)
    return TeamSummary.model_validate(
        detail.model_dump(exclude={"owner_account_id", "contest"}, by_alias=False)
    )


async def list_teams(
    session: AsyncSession,
    search: TeamSearch,
    *,
    contest_id: UUID | None = None,
    require_contest: bool = False,
    now: datetime | None = None,
) -> Page[TeamSummary]:
    """페이지 보정·총원·목록을 한 문장에서 읽어 동시 변경에 의한 혼합을 막는다.

    공고 하위 경로는 공고 존재 여부도 같은 문장에서 확인한다. 이 함수는
    세션의 격리 수준을 바꾸거나 트랜잭션을 시작·종료하지 않는다.
    """
    current = _utcnow() if now is None else now
    members = _member_count()
    matches = select(Team.team_id, Team.created_at).join(
        Contest, Contest.contest_id == Team.contest_id
    )
    if contest_id is not None:
        matches = matches.where(Team.contest_id == contest_id)
    if search.role_code is not None:
        matches = matches.where(
            select(TeamRecruitmentRole.team_id)
            .where(
                TeamRecruitmentRole.team_id == Team.team_id,
                TeamRecruitmentRole.role_code == search.role_code.value,
            )
            .exists()
        )
    if search.recruiting_only:
        matches = matches.where(
            Team.recruitment_state == "open",
            Contest.registration_opens_at <= current,
            Contest.registration_closes_at > current,
            Team.recruitment_closes_at > current,
            members < Team.target_capacity,
        )
    needle = (search.q or "").strip()
    if needle:
        matching_roles = [
            role.value
            for role in RoleCode
            if needle.casefold() in role.display_name.casefold()
        ]
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
    last_page = (stats.c.total + search.page_size - 1) // search.page_size
    bounded = select(
        stats.c.total,
        func.greatest(1, func.least(search.page, last_page)).label("page"),
    ).cte("team_page_bounds")
    page_ids = (
        select(matching.c.team_id)
        .order_by(matching.c.created_at.desc(), matching.c.team_id.desc())
        .limit(search.page_size)
        .offset(select((bounded.c.page - 1) * search.page_size).scalar_subquery())
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
    if not found:
        raise AppError(404, "CONTEST_NOT_FOUND", "공고를 찾을 수 없습니다.")
    items = [
        build_team_summary(
            team,
            contest,
            field_codes=fields or [],
            role_codes=roles or [],
            member_count=count,
            now=current,
        )
        for team, contest, count, roles, fields, *_ in rows
        if team is not None
    ]
    return Page(
        data=items,
        pagination=PageMeta(
            page=page,
            page_size=search.page_size,
            total=total,
            total_pages=(total + search.page_size - 1) // search.page_size,
        ),
    )
