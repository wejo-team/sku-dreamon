"""공개 팀과 현재 집계를 한 SQL 읽기 시점에서 조회한다."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, literal, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect

from app.core.demo_data import is_demo_team
from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.contests import Contest, ContestField
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.queries.contests import build_contest_summary
from app.rules.catalogs import FieldCode, RoleCode
from app.schemas.contests import DeadlineInterpretation
from app.schemas.teams import TeamDetail, TeamSearch, TeamSummary


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


def build_team_summary(
    team: Team,
    contest: Contest,
    *,
    field_codes: Sequence[str],
    role_codes: Sequence[str],
    member_count: int,
    now: datetime,
) -> TeamSummary:
    """같은 조회 시점의 실제 인원·분류를 받으며 개인의 지원 성공을 추정하지 않는다."""
    return TeamSummary(
        id=team.team_id,
        version=str(team.version),
        contest_id=contest.contest_id,
        contest_title=contest.title,
        name=team.name,
        introduction=team.introduction,
        field_codes=sorted(
            (FieldCode(code) for code in field_codes), key=lambda code: code.sort_order
        ),
        role_codes=sorted(
            (RoleCode(code) for code in role_codes), key=lambda code: code.sort_order
        ),
        capacity=str(team.target_capacity),
        member_count=member_count,
        recruitment_state=team.recruitment_state,
        closed_reason=team.closed_reason,
        recruitment_ends_at=team.recruitment_closes_at,
        is_recruiting=(
            team.recruitment_state == "open"
            and contest.registration_opens_at <= now < contest.registration_closes_at
            and now < team.recruitment_closes_at
            and member_count < team.target_capacity
        ),
        is_demo=is_demo_team(team.team_id),
        created_at=team.created_at,
        recruitment_deadline=DeadlineInterpretation(
            source_date=team.deadline_source_date,
            source_time=(
                None
                if team.deadline_source_time is None
                else team.deadline_source_time.isoformat()
            ),
            source_time_zone=team.deadline_source_timezone,
            effective_time_zone=team.deadline_effective_timezone,
            time_defaulted=team.deadline_time_assumed,
            time_zone_defaulted=team.deadline_timezone_assumed,
        ),
    )
