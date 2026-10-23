"""실제 공고를 공개 팀 상세의 공고 요약과 마감 안내로 변환한다."""

from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from pydantic import HttpUrl

from app.core.http.schemas import NonnegativeInt, ResponseDTO, Timestamp, Version
from app.domains.catalogs.codes import FieldCode
from app.domains.contests.models import Contest
from app.domains.contests.rules import RegistrationStatus, get_registration_status
from app.domains.demo.manifest import is_demo_contest


class DeadlineInterpretation(ResponseDTO):
    source_date: date
    source_time: str | None
    source_time_zone: str | None
    effective_time_zone: str
    time_defaulted: bool
    time_zone_defaulted: bool


class ContestSummary(ResponseDTO):
    id: UUID
    title: str
    organizer: str
    field_codes: list[FieldCode]
    poster_url: HttpUrl | None
    registration_status: RegistrationStatus
    starts_at: Timestamp
    ends_at: Timestamp
    team_count: NonnegativeInt
    is_demo: bool
    created_at: Timestamp
    version: Version


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
        poster_url=None if contest.poster_url is None else HttpUrl(contest.poster_url),
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
