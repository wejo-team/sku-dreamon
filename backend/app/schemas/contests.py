"""공개 공고 요약·상세와 원문 인원·일정 안내의 전송 계약을 정의한다."""

from datetime import date
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
from app.rules.catalogs import FieldCode
from app.rules.contests import (
    AudienceCode,
    CapacityKind,
    RegistrationStatus,
    validate_audience_codes,
    validate_participation_capacity,
)


class DeadlineInterpretation(ResponseDTO):
    """마감의 원문 정보와 서비스가 보완한 시각·시간대 안내."""

    source_date: date = Field(description="원문 또는 사용자가 입력한 마감 날짜.")
    source_time: str | None = Field(
        description="원문 마감 시각. 원문에 없으면 null입니다."
    )
    source_time_zone: str | None = Field(
        description="원문 마감 시간대. 원문에 없으면 null입니다."
    )
    effective_time_zone: str = Field(description="실제 마감 경계 계산에 적용한 시간대.")
    time_defaulted: bool = Field(
        description=("원문 시각이 없어 해당 날짜 끝까지로 마감을 보완했는지 여부.")
    )
    time_zone_defaulted: bool = Field(
        description="원문 시간대가 없어 한국시간으로 보완했는지 여부."
    )


class ContestSummary(ResponseDTO):
    """공개 공고의 접수 상태와 연결 팀 수를 포함한 요약."""

    id: UUID = Field(description="공고의 UUID.")
    title: str = Field(description="공고 제목.")
    organizer: str = Field(description="공모전 주최자.")
    field_codes: list[FieldCode] = Field(description="공고의 분야 코드 목록.")
    poster_url: AnyHttpUrl | None = Field(
        description=("포스터의 HTTP(S) 주소. 포스터가 없으면 null입니다.")
    )
    registration_status: RegistrationStatus = Field(
        description=(
            "현재 접수 상태. scheduled는 시작 전, open은 "
            "접수 중, closed는 접수 마감입니다."
        )
    )
    starts_at: Timestamp = Field(
        description="접수 시작 시각의 포함 경계. UTC 기준입니다."
    )
    ends_at: Timestamp = Field(
        description=(
            "접수 마감 시각의 제외 경계. 이 시각부터 접수가 마감되며 UTC 기준입니다."
        )
    )
    team_count: NonnegativeInt = Field(
        description="모집 상태와 관계없이 이 공고에 연결된 전체 팀 수."
    )
    is_demo: bool = Field(
        description=(
            "공고용 고정 UUID 시드 목록을 기준으로 서버가 판정한 시연용 공고 여부."
        )
    )
    created_at: Timestamp = Field(description="공고 등록 시각. UTC 기준입니다.")
    version: Version = Field(
        description="현재 공고 버전. 양의 정수를 나타내는 십진 문자열입니다."
    )


class ParticipationCapacity(ResponseDTO):
    """원문에 명시된 참가 인원 범위와 정보 확인 상태."""

    kind: CapacityKind = Field(
        description=(
            "인원 조건 종류. range는 범위, unlimited는 "
            "최대 제한 없음, unknown은 미확인입니다."
        )
    )
    minimum_members: PositiveBigInt | None = Field(
        description=(
            "최소 참가 인원의 양의 십진 문자열. 확인된 최소가 없으면 null입니다."
        )
    )
    maximum_members: PositiveBigInt | None = Field(
        description=(
            "최대 참가 인원의 양의 십진 문자열. 최대 제한이 없거나 "
            "미확인이면 null입니다."
        )
    )

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
    """공고 접수 경계와 원문 일정·시간대 보완 정보."""

    starts_at: Timestamp = Field(
        description=("상위 공고의 startsAt과 같은 접수 시작 포함 경계. UTC 기준입니다.")
    )
    ends_at: Timestamp = Field(
        description=("상위 공고의 endsAt과 같은 접수 마감 제외 경계. UTC 기준입니다.")
    )
    open_source_date: date = Field(description="원문 접수 시작 날짜.")
    open_source_time: str | None = Field(
        description="원문 접수 시작 시각. 원문에 없으면 null입니다."
    )
    open_source_time_zone: str | None = Field(
        description="원문 접수 시작 시간대. 원문에 없으면 null입니다."
    )
    open_effective_time_zone: str = Field(
        description="접수 시작 경계 계산에 적용한 시간대."
    )
    open_time_zone_defaulted: bool = Field(
        description="원문 시작 시간대가 없어 서비스 기준으로 보완했는지 여부."
    )
    closing: DeadlineInterpretation = Field(
        description="접수 마감의 원문 정보와 시각·시간대 보완 여부."
    )


class ContestDetail(ContestSummary):
    """공개 공고 요약과 참가 조건·공식 원문을 포함한 상세 정보."""

    field_codes: list[FieldCode] = Field(
        max_length=3, description="공고의 분야 코드 목록. 최대 3개입니다."
    )
    description: str | None = Field(
        description="공고 상세 설명. 제공된 설명이 없으면 null입니다."
    )
    audience_codes: list[AudienceCode] = Field(
        min_length=1,
        max_length=2,
        description=(
            "참가 대상 코드. student와 general은 함께 "
            "가능하며 unrestricted와 unknown은 단독으로 "
            "사용합니다."
        ),
    )
    eligibility_text: str = Field(description="공식 원문의 참가 자격 조건.")
    capacity: ParticipationCapacity = Field(
        description="공식 원문의 참가 인원 조건과 확인 상태."
    )
    timing: ContestTiming = Field(
        description="접수 일정의 원문과 서비스가 보완한 정보."
    )
    deliverables: str | None = Field(
        description="제출물 안내. 제공된 안내가 없으면 null입니다."
    )
    awards: str | None = Field(
        description="시상 안내. 제공된 안내가 없으면 null입니다."
    )
    contact: str | None = Field(
        description="문의처 안내. 제공된 안내가 없으면 null입니다."
    )
    verified_at: Timestamp = Field(
        description="등록 전에 공고 자료를 확인한 시각. UTC 기준입니다."
    )
    source_url: AnyHttpUrl = Field(description="공식 공고 원문의 HTTP(S) URL.")

    @field_validator("audience_codes")
    @classmethod
    def validate_audiences(cls, codes: list[AudienceCode]) -> list[AudienceCode]:
        return list(validate_audience_codes(codes))
