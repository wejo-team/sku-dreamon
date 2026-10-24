"""팀의 공개 응답과 모집·소속 업무 규칙 및 트랜잭션을 관리한다."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demo_data import is_demo_team
from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.contests import Contest
from app.models.teams import Team, TeamMembership
from app.repositories import teams as repository
from app.rules.catalogs import FieldCode, RoleCode
from app.schemas.contests import DeadlineInterpretation
from app.schemas.teams import TeamDetail, TeamSearch, TeamSummary
from app.services.contests import build_contest_summary


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def get_team_detail(
    session: AsyncSession, team_id: UUID, *, now: datetime | None = None
) -> TeamDetail:
    """호출자의 트랜잭션을 유지하며 공개 필드와 전체 팀 수를 함께 읽는다."""
    current = _utcnow() if now is None else now
    row = await repository.get_team_detail(session, team_id)
    if row is None:
        raise AppError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다.")
    team, contest, count, roles, fields = row.team
    team_count = row.team_count
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
    needle = (search.q or "").strip()
    result = await repository.list_teams(
        session,
        page=search.page,
        page_size=search.page_size,
        role_code=None if search.role_code is None else search.role_code.value,
        recruiting_only=search.recruiting_only,
        needle=needle,
        matching_roles=[
            role.value
            for role in RoleCode
            if needle.casefold() in role.display_name.casefold()
        ],
        contest_id=contest_id,
        require_contest=require_contest,
        current=current,
    )
    total, page, found = result.total, result.page, result.contest_exists
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
        for team, contest, count, roles, fields in result.rows
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


def end_application_membership(
    team: Team, membership: TeamMembership | None, *, now: datetime
) -> None:
    """호출자가 잠근 팀의 선발 소속을 종료하며 모집 상태는 보존한다."""
    if membership is None or membership.ended_at is not None:
        raise RuntimeError("Selected application requires active membership")
    membership.ended_at = now
    membership.end_reason = "application_canceled"
    team.version += 1
    team.updated_at = now
