"""실제 공고를 공개 팀 상세의 공고 요약과 마감 안내로 변환한다."""

from datetime import date
from uuid import UUID

from pydantic import HttpUrl

from app.core.http.schemas import NonnegativeInt, ResponseDTO, Timestamp, Version
from app.rules.catalogs import FieldCode
from app.rules.contests import RegistrationStatus


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
