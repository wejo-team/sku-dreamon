"""공개 팀 검색 조건과 관계 정보가 없는 모집글 DTO를 정의한다."""

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.core.http.schemas import (
    PositiveBigInt,
    PositiveInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
    Version,
)
from app.domains.catalogs.codes import FieldCode, RoleCode
from app.domains.contests.models import Contest
from app.domains.contests.schemas import ContestSummary, DeadlineInterpretation
from app.domains.demo.manifest import is_demo_team
from app.domains.teams.models import Team


class TeamSearch(RequestDTO):
    page: Annotated[int, Field(ge=1, le=9007199254740991)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20
    q: str | None = None
    role_code: RoleCode | None = None
    recruiting_only: bool = False


class AllTeamSearch(TeamSearch):
    contest_id: UUID | None = None


class TeamSummary(ResponseDTO):
    id: UUID
    version: Version
    contest_id: UUID
    contest_title: str
    name: str
    introduction: str
    field_codes: list[FieldCode]
    role_codes: list[RoleCode]
    capacity: PositiveBigInt
    member_count: PositiveInt
    recruitment_state: Literal["open", "closed"]
    closed_reason: Literal["capacity_reached", "leader_closed"] | None
    recruitment_ends_at: Timestamp
    is_recruiting: bool
    is_demo: bool
    created_at: Timestamp
    recruitment_deadline: DeadlineInterpretation


class TeamDetail(TeamSummary):
    owner_account_id: UUID
    contest: ContestSummary


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
