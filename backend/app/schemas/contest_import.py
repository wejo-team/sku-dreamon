"""확인된 공고의 운영 입력을 검증하고 원문 일정과 적용 경계를 연결한다."""

import re
from datetime import date as Date
from datetime import time as Time
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StrictStr, field_validator, model_validator

from app.core.http.schemas import PositiveBigInt, RequestDTO, Timestamp
from app.rules.catalogs import FieldCode
from app.rules.contests import (
    AudienceCode,
    ResolvedDeadline,
    interpret_deadline,
    validate_audience_codes,
    validate_field_codes,
    validate_participation_capacity,
)


def _storable_text(value: str) -> str:
    if "\x00" in value:
        raise ValueError("NUL is not supported")
    value.encode("utf-8")
    return value


def _required_text(value: str) -> str:
    if not value.strip():
        raise ValueError("Confirmed text is required")
    return value


def _http_url(value: str) -> str:
    from pydantic import AnyHttpUrl, TypeAdapter

    TypeAdapter(AnyHttpUrl).validate_python(value)
    return value


SourceText = Annotated[StrictStr, AfterValidator(_storable_text)]
RequiredText = Annotated[SourceText, AfterValidator(_required_text)]
SourceUrl = Annotated[RequiredText, AfterValidator(_http_url)]


class SourceDeadline(RequestDTO):
    """원문 날짜·선택 시각·시간대를 보존하며 확정된 마감 보완만 적용한다."""

    date: Date = Field(description="원문의 실제 달력 날짜.")
    time: str | None = Field(description="원문 HH:mm 또는 HH:mm:ss. 없으면 null.")
    time_zone: str | None = Field(description="원문 IANA 시간대 또는 UTC offset.")

    @field_validator("date", mode="before")
    @classmethod
    def require_date(cls, value: object) -> object:
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            raise ValueError("Calendar date is required")
        return value

    @field_validator("time")
    @classmethod
    def require_time(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(
            r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?", value
        ):
            raise ValueError("Local clock time is required")
        return value

    def resolve(self) -> ResolvedDeadline:
        return interpret_deadline(
            source_date=self.date,
            source_time=None if self.time is None else Time.fromisoformat(self.time),
            source_timezone=self.time_zone,
        )


class ConfirmedCapacity(RequestDTO):
    """등록 가능한 확인 완료 인원 조건. 미확인 값을 허용하지 않는다."""

    kind: Literal["range", "unlimited"] = Field(
        description="확인된 범위 또는 상한 없음."
    )
    minimum_members: PositiveBigInt | None = Field(description="확인된 최소 인원.")
    maximum_members: PositiveBigInt | None = Field(description="확인된 최대 인원.")

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        validate_participation_capacity(
            kind=self.kind,
            minimum_members=None
            if self.minimum_members is None
            else int(self.minimum_members),
            maximum_members=None
            if self.maximum_members is None
            else int(self.maximum_members),
        )
        return self


class ContestImport(RequestDTO):
    """관리자가 확인한 공고 한 건. 입력 자료를 임의 요약·절단하지 않는다."""

    title: RequiredText = Field(description="확인된 공모전명.")
    organizer: RequiredText = Field(description="확인된 주최 기관명.")
    source_url: SourceUrl = Field(description="공식 HTTP(S) 원문 주소.")
    eligibility_text: RequiredText = Field(description="원문 참가 조건.")
    audience_codes: list[AudienceCode] = Field(description="확인된 참가 대상.")
    field_codes: list[FieldCode] = Field(description="공통 분야 코드. 최대 3개.")
    capacity: ConfirmedCapacity = Field(description="확인된 공식 인원 조건.")
    opening: SourceDeadline = Field(description="확인된 시작 날짜·시각. 시각은 필수.")
    closing: SourceDeadline = Field(
        description="마감 원문. 날짜 끝·한국시간 보완 허용."
    )
    verified_at: Timestamp = Field(description="원문 확인 완료 시각.")
    description: SourceText | None = Field(description="확인된 설명 또는 null.")
    deliverables: SourceText | None = Field(description="제출물 또는 null.")
    awards: SourceText | None = Field(description="시상 정보 또는 null.")
    contact: SourceText | None = Field(description="문의 정보 또는 null.")
    poster_url: SourceUrl | None = Field(description="포스터 HTTP(S) 주소 또는 null.")

    @model_validator(mode="after")
    def validate_confirmed_source(self) -> Self:
        validate_audience_codes(self.audience_codes)
        if AudienceCode.UNKNOWN in self.audience_codes:
            raise ValueError("Audience must be confirmed")
        validate_field_codes(self.field_codes)
        if self.opening.time is None:
            raise ValueError("Opening time must be confirmed")
        if self.opening.resolve().ends_at >= self.closing.resolve().ends_at:
            raise ValueError("Opening must precede closing")
        return self
