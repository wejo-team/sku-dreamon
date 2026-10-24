"""팀 생성의 정원·역할·원문 마감과 정규화 입력 계약을 정의한다."""

import re
from datetime import date as Date
from datetime import time as Time
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, Field, StrictStr, field_validator, model_validator

from app.core.http.schemas import PositiveBigInt, RequestDTO
from app.rules.contests import ResolvedDeadline, interpret_deadline
from app.rules.text import normalize_text

Text = Annotated[StrictStr, AfterValidator(normalize_text)]


class DeadlineInput(RequestDTO):
    """명시한 원문 날짜·시각·시간대와 확정된 마감 보완만 사용한다."""

    date: Date = Field(description="마감 날짜 YYYY-MM-DD.")
    time: str | None = Field(
        default=None, description="HH:mm 또는 HH:mm:ss. 없으면 날짜 끝."
    )
    time_zone: str | None = Field(
        default=None, description="IANA 시간대 또는 ±HH:MM. 없으면 한국시간."
    )

    @field_validator("date", mode="before")
    @classmethod
    def calendar_date(cls, value: object) -> object:
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            raise ValueError("Calendar date is required")
        return value

    @field_validator("time")
    @classmethod
    def clock_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?", value):
            raise ValueError("Local clock time is required")
        return Time.fromisoformat(value).isoformat()

    def resolve(self) -> ResolvedDeadline:
        return interpret_deadline(
            source_date=self.date,
            source_time=None if self.time is None else Time.fromisoformat(self.time),
            source_timezone=self.time_zone,
        )

    @model_validator(mode="after")
    def unambiguous_deadline(self) -> Self:
        self.resolve()
        return self


class TeamCreate(RequestDTO):
    """한 번의 팀 생성 행동과 동일 요청 재전송을 구분한다."""

    request_id: UUID = Field(description="생성 시도 UUID. 재전송은 동일 ID.")
    contest_id: UUID = Field(description="대상 공고 UUID.")
    name: Annotated[Text, Field(min_length=2, max_length=40)] = Field(
        description="팀명. NFC·trim 후 2~40 코드 포인트."
    )
    introduction: Annotated[Text, Field(min_length=10, max_length=1000)] = Field(
        description="소개·목표. 10~1000 코드 포인트."
    )
    capacity: PositiveBigInt = Field(description="팀장을 포함한 목표 정원.")
    role_codes: list[StrictStr] = Field(
        max_length=6, description="정원 1이면 빈 목록, 그 외 역할 1~6개."
    )
    recruitment_deadline: DeadlineInput = Field(description="모집 마감 원문.")

    @model_validator(mode="after")
    def roles_match_capacity(self) -> Self:
        if len(set(self.role_codes)) != len(self.role_codes):
            raise ValueError("Roles must be distinct")
        if (int(self.capacity) == 1) != (len(self.role_codes) == 0):
            raise ValueError("Roles must match capacity")
        self.role_codes.sort()
        return self
