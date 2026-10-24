"""실제 공고를 공개 팀 상세의 공고 요약과 마감 안내로 변환한다."""

from datetime import date
from uuid import UUID

from pydantic import Field, HttpUrl

from app.core.http.schemas import NonnegativeInt, ResponseDTO, Timestamp, Version
from app.rules.catalogs import FieldCode
from app.rules.contests import RegistrationStatus


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
    poster_url: HttpUrl | None = Field(
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
