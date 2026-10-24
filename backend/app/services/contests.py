"""공개 공고의 상태·원문 응답을 같은 조회 시점의 저장 자료로 구성한다."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import begin_read_snapshot
from app.core.demo_data import is_demo_contest
from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.contests import Contest
from app.repositories import contest_list as listing
from app.repositories import contests as repository
from app.rules.catalogs import FieldCode
from app.rules.contests import AudienceCode, CapacityKind, get_registration_status
from app.schemas.contests import (
    ContestDetail,
    ContestSearch,
    ContestSummary,
    ContestTiming,
    DeadlineInterpretation,
    ParticipationCapacity,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def list_contests(
    session: AsyncSession, query: ContestSearch
) -> Page[ContestSummary]:
    if session.in_transaction():
        raise RuntimeError("Contest listing requires a fresh transaction")
    await begin_read_snapshot(session, read_only=True)
    current = _utcnow()
    needle = (query.q or "").strip()
    filters = listing.ContestFilter(
        needle=needle,
        matching_fields=[
            code.value
            for code in FieldCode
            if needle.casefold() in code.display_name.casefold()
        ],
        field_code=query.field_code,
        registration_status=query.registration_status,
        now=current,
    )
    total = await listing.count_contests(session, filters)
    pages = (total + query.page_size - 1) // query.page_size
    page = min(query.page, max(pages, 1))
    rows = await listing.list_contests(
        session, filters, sort=query.sort, page=page, page_size=query.page_size
    )
    return Page(
        data=[
            build_contest_summary(
                row.contest,
                field_codes=row.field_codes,
                team_count=row.team_count,
                now=current,
            )
            for row in rows
        ],
        pagination=PageMeta(
            page=page, page_size=query.page_size, total=total, total_pages=pages
        ),
    )


async def get_contest_detail(
    session: AsyncSession, contest_id: UUID, *, now: datetime | None = None
) -> ContestDetail:
    """접수 상태와 무관하게 공개 원문을 읽고 호출자의 트랜잭션은 유지한다."""
    current = _utcnow() if now is None else now
    row = await repository.get_contest_detail(session, contest_id)
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
