"""공개 공고 요약·상세와 원문 인원·일정 안내의 전송 계약을 정의한다."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from app.core.http.schemas import (
    NonnegativeInt,
    PositiveBigInt,
    ResponseDTO,
    Timestamp,
    Version,
)
from app.domains.catalogs.codes import FieldCode
from app.domains.contests.models import Contest
from app.domains.contests.rules import (
    AudienceCode,
    CapacityKind,
    RegistrationStatus,
    get_registration_status,
    validate_audience_codes,
    validate_participation_capacity,
)
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
    poster_url: AnyHttpUrl | None
    registration_status: RegistrationStatus
    starts_at: Timestamp
    ends_at: Timestamp
    team_count: NonnegativeInt
    is_demo: bool
    created_at: Timestamp
    version: Version


class ParticipationCapacity(ResponseDTO):
    kind: CapacityKind
    minimum_members: PositiveBigInt | None
    maximum_members: PositiveBigInt | None

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        validate_participation_capacity(
            kind=self.kind,
            minimum_members=(
                None if self.minimum_members is None else int(self.minimum_members)
            ),
            maximum_members=(
                None if self.maximum_members is None else int(self.maximum_members)
            ),
        )
        return self


class ContestTiming(ResponseDTO):
    starts_at: Timestamp
    ends_at: Timestamp
    open_source_date: date
    open_source_time: str | None
    open_source_time_zone: str | None
    open_effective_time_zone: str
    open_time_zone_defaulted: bool
    closing: DeadlineInterpretation


class ContestDetail(ContestSummary):
    field_codes: list[FieldCode] = Field(max_length=3)
    description: str | None
    audience_codes: list[AudienceCode] = Field(min_length=1, max_length=2)
    eligibility_text: str
    capacity: ParticipationCapacity
    timing: ContestTiming
    deliverables: str | None
    awards: str | None
    contact: str | None
    verified_at: Timestamp
    source_url: AnyHttpUrl

    @field_validator("audience_codes")
    @classmethod
    def validate_audiences(cls, codes: list[AudienceCode]) -> list[AudienceCode]:
        return list(validate_audience_codes(codes))


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
