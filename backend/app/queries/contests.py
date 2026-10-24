"""공개 공고 원문과 분류·연결 팀 수를 한 SQL 읽기 시점에서 조회한다."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import AnyHttpUrl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demo_data import is_demo_contest
from app.core.exceptions import AppError
from app.models.contests import Contest, ContestAudience, ContestField
from app.models.teams import Team
from app.rules.catalogs import FieldCode
from app.rules.contests import AudienceCode, CapacityKind, get_registration_status
from app.schemas.contests import (
    ContestDetail,
    ContestSummary,
    ContestTiming,
    DeadlineInterpretation,
    ParticipationCapacity,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def get_contest_detail(
    session: AsyncSession, contest_id: UUID, *, now: datetime | None = None
) -> ContestDetail:
    """접수 상태와 무관하게 공개 원문을 읽고 호출자의 트랜잭션은 유지한다."""
    current = _utcnow() if now is None else now
    fields = (
        select(func.array_agg(ContestField.field_code))
        .where(ContestField.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    audiences = (
        select(func.array_agg(ContestAudience.audience_code))
        .where(ContestAudience.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    team_count = (
        select(func.count())
        .select_from(Team)
        .where(Team.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(Contest, fields, audiences, team_count)
            .where(Contest.contest_id == contest_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "CONTEST_NOT_FOUND", "공고를 찾을 수 없습니다.")
    contest, field_codes, audience_codes, count = row
    summary = build_contest_summary(
        contest, field_codes=field_codes or [], team_count=count, now=current
    )
    return ContestDetail(
        **summary.model_dump(by_alias=False),
        description=contest.description,
        audience_codes=sorted(
            (AudienceCode(code) for code in audience_codes or []),
            key=list(AudienceCode).index,
        ),
        eligibility_text=contest.eligibility_text,
        capacity=ParticipationCapacity(
            kind=CapacityKind(contest.member_limit_kind),
            minimum_members=(
                None if contest.min_members is None else str(contest.min_members)
            ),
            maximum_members=(
                None if contest.max_members is None else str(contest.max_members)
            ),
        ),
        timing=ContestTiming(
            starts_at=contest.registration_opens_at,
            ends_at=contest.registration_closes_at,
            open_source_date=contest.open_source_date,
            open_source_time=(
                None
                if contest.open_source_time is None
                else contest.open_source_time.isoformat()
            ),
            open_source_time_zone=contest.open_source_timezone,
            open_effective_time_zone=contest.open_effective_timezone,
            open_time_zone_defaulted=contest.open_timezone_assumed,
            closing=DeadlineInterpretation(
                source_date=contest.close_source_date,
                source_time=(
                    None
                    if contest.close_source_time is None
                    else contest.close_source_time.isoformat()
                ),
                source_time_zone=contest.close_source_timezone,
                effective_time_zone=contest.close_effective_timezone,
                time_defaulted=contest.close_time_assumed,
                time_zone_defaulted=contest.close_timezone_assumed,
            ),
        ),
        deliverables=contest.submission_details,
        awards=contest.awards,
        contact=contest.contact_info,
        verified_at=contest.verified_at,
        source_url=AnyHttpUrl(contest.official_url),
    )


def build_contest_summary(
    contest: Contest,
    *,
    field_codes: Sequence[str],
    team_count: int,
    now: datetime,
) -> ContestSummary:
    """호출자가 같은 조회 시점에서 구한 분야·전체 팀 수로 공고 요약을 만든다."""
    return ContestSummary(
        id=contest.contest_id,
        title=contest.title,
        organizer=contest.organizer_name,
        field_codes=sorted(
            (FieldCode(code) for code in field_codes), key=lambda code: code.sort_order
        ),
        poster_url=None
        if contest.poster_url is None
        else AnyHttpUrl(contest.poster_url),
        registration_status=get_registration_status(
            starts_at=contest.registration_opens_at,
            ends_at=contest.registration_closes_at,
            now=now,
        ),
        starts_at=contest.registration_opens_at,
        ends_at=contest.registration_closes_at,
        team_count=team_count,
        is_demo=is_demo_contest(contest.contest_id),
        created_at=contest.created_at,
        version=str(contest.version),
    )
