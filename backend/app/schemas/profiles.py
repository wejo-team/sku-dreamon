"""읽기 전용 프로필 DTO와 공개 사람 탐색의 query 계약을 정의한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field

from app.core.http.schemas import (
    PositiveBigInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
    Version,
)
from app.rules.catalogs import (
    AcademicStatusCode,
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)


class PortfolioResponse(ResponseDTO):
    """프로필에 등록된 포트폴리오 링크와 선택 제목."""

    url: AnyHttpUrl = Field(description="등록된 포트폴리오의 HTTP(S) 절대 URL.")
    title: str | None = Field(
        description="포트폴리오의 선택 제목. 미입력 시 null입니다."
    )


class PersonSummary(ResponseDTO):
    """사람 목록에서 사용하는 프로필 요약 정보."""

    account_id: UUID = Field(description="프로필 소유 계정의 UUID.")
    real_name: str = Field(description="프로필 소유자의 실명.")
    is_demo: bool = Field(
        description=(
            "계정용 고정 UUID 시드 목록을 기준으로 서버가 판정한 시연용 계정 여부."
        )
    )
    profile_image_code: ProfileImageCode | None = Field(
        description=("공통 프로필 이미지 선택지 코드. 미선택 시 null입니다.")
    )
    introduction: str | None = Field(description="자기소개. 미입력 시 null입니다.")
    field_codes: Annotated[
        list[FieldCode],
        Field(min_length=1, max_length=3, description="관심 분야 코드 목록."),
    ]
    role_codes: Annotated[
        list[RoleCode],
        Field(min_length=1, max_length=2, description="희망 역할 코드 목록."),
    ]
    skill_codes: list[SkillCode] = Field(
        description=("보유 역량 코드 목록. 선택한 역량이 없으면 빈 배열입니다.")
    )


class ProfileResponse(PersonSummary):
    """조회 권한이 있는 사용자에게 제공하는 최신 전체 프로필."""

    version: Version = Field(
        description=("현재 프로필 버전. 양의 정수를 나타내는 십진 문자열입니다.")
    )
    is_public: bool = Field(description="현재 전체 프로필의 공개 여부.")
    updated_at: Timestamp = Field(
        description="프로필을 마지막으로 변경한 시각. UTC 기준입니다."
    )
    academic_status_code: AcademicStatusCode | None = Field(
        description="학적 상태 선택지 코드. 미입력 시 null입니다."
    )
    grade_code: GradeCode | None = Field(
        description="학년 선택지 코드. 미입력 시 null입니다."
    )
    weekly_availability_code: WeeklyAvailabilityCode | None = Field(
        description=("주당 참여 가능 시간 구간 코드. 미입력 시 null입니다.")
    )
    academic_unit_id: PositiveBigInt | None = Field(
        description=(
            "가장 깊게 선택한 학사 항목 ID의 십진 문자열. 미선택 시 null입니다."
        )
    )
    experience_state: Literal["unspecified", "none", "provided"] = Field(
        description=(
            "경험 입력 상태. unspecified는 미입력, "
            "none은 경험 없음, provided는 본문 입력입니다."
        )
    )
    experience_body: str | None = Field(
        description=("경험 본문. 경험 상태가 provided가 아니면 null입니다.")
    )
    portfolio: PortfolioResponse | None = Field(
        description=("등록된 포트폴리오 링크와 선택 제목. 미등록 시 null입니다.")
    )


class PeopleQuery(RequestDTO):
    """공개 사람 목록의 검색·필터·페이지 조건."""

    q: str | None = Field(
        default=None,
        description=(
            "사람 검색어. 앞뒤 공백을 제거하며 생략하거나 빈 값이면 "
            "검색어 제한이 없습니다."
        ),
    )
    field_code: FieldCode | None = Field(
        default=None,
        description=("관심 분야에 포함되어야 하는 코드. 생략 시 분야 제한이 없습니다."),
    )
    role_code: RoleCode | None = Field(
        default=None,
        description=("희망 역할에 포함되어야 하는 코드. 생략 시 역할 제한이 없습니다."),
    )
    page: Annotated[
        int,
        Field(
            ge=1,
            le=9007199254740991,
            description=(
                "요청 페이지 번호. 1부터 시작하며 마지막 페이지를 넘으면 "
                "마지막 유효 페이지로 보정합니다."
            ),
        ),
    ] = 1
    page_size: Annotated[
        int,
        Field(
            ge=1,
            le=100,
            description="페이지당 항목 수. 1~100개이며 기본값은 20개입니다.",
        ),
    ] = 20
