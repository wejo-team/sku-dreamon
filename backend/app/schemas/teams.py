"""공개 팀 검색 조건과 관계 정보가 없는 모집글 DTO를 정의한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.core.http.schemas import (
    PositiveBigInt,
    PositiveInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
    Version,
)
from app.rules.catalogs import FieldCode, RoleCode
from app.schemas.contests import ContestSummary, DeadlineInterpretation


class TeamSearch(RequestDTO):
    """공개 팀 목록의 검색·모집 필터·페이지 조건."""

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
    q: str | None = Field(
        default=None,
        description=(
            "팀 검색어. 앞뒤 공백을 제거하며 생략하거나 빈 값이면 "
            "검색어 제한이 없습니다."
        ),
    )
    role_code: RoleCode | None = Field(
        default=None,
        description=("모집 역할에 포함되어야 하는 코드. 생략 시 역할 제한이 없습니다."),
    )
    recruiting_only: bool = Field(
        default=False,
        description=("true이면 서버의 공통 모집 가능 조건을 충족하는 팀만 조회합니다."),
    )

    @field_validator("q")
    @classmethod
    def validate_search_text(cls, value: str | None) -> str | None:
        if value is not None:
            # PostgreSQL text는 NUL과 UTF-8로 표현할 수 없는 문자를 받지 않는다.
            if "\x00" in value:
                raise ValueError("검색어에 사용할 수 없는 문자가 있습니다.")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ValueError("검색어에 사용할 수 없는 문자가 있습니다.") from error
        return value


class AllTeamSearch(TeamSearch):
    """전체 공개 팀 목록에서 공고별 필터를 포함한 검색 조건."""

    contest_id: UUID | None = Field(
        default=None,
        description=("조회할 팀이 속한 공고 UUID. 생략 시 공고 제한이 없습니다."),
    )


class TeamSummary(ResponseDTO):
    """팀 모집글의 요약과 현재 모집 가능 여부."""

    id: UUID = Field(description="팀의 UUID.")
    version: Version = Field(
        description="현재 팀 버전. 양의 정수를 나타내는 십진 문자열입니다."
    )
    contest_id: UUID = Field(description="연결된 공고의 UUID.")
    contest_title: str = Field(description="연결된 공고의 제목.")
    name: str = Field(description="팀 이름.")
    introduction: str = Field(description="팀 소개와 활동 목표.")
    field_codes: list[FieldCode] = Field(description="연결된 공고의 분야 코드 목록.")
    role_codes: list[RoleCode] = Field(description="팀이 모집하는 역할 코드 목록.")
    capacity: PositiveBigInt = Field(
        description="팀장을 포함한 목표 정원. 양의 십진 문자열입니다."
    )
    member_count: PositiveInt = Field(
        description="현재 팀장과 확정 팀원을 합한 인원 수."
    )
    recruitment_state: Literal["open", "closed"] = Field(
        description=(
            "저장된 모집 상태. open은 모집 중, closed는 "
            "모집 종료이며 현재 접수 가능 여부는 "
            "isRecruiting으로 확인합니다."
        )
    )
    closed_reason: Literal["capacity_reached", "leader_closed"] | None = Field(
        description=(
            "모집 종료 사유. capacity_reached는 정원 "
            "도달, leader_closed는 팀장 종료이며 "
            "open이면 null입니다."
        )
    )
    recruitment_ends_at: Timestamp = Field(
        description=(
            "팀 모집 마감의 제외 경계. 이 시각부터 모집할 수 없으며 UTC 기준입니다."
        )
    )
    is_recruiting: bool = Field(
        description=(
            "기한·정원 등을 반영해 서버가 계산한 공통 모집 가능 "
            "여부. 특정 사용자의 지원 성공을 보장하지 않습니다."
        )
    )
    is_demo: bool = Field(
        description=(
            "팀용 고정 UUID 시드 목록을 기준으로 서버가 판정한 시연용 팀 여부."
        )
    )
    created_at: Timestamp = Field(description="팀 생성 시각. UTC 기준입니다.")
    recruitment_deadline: DeadlineInterpretation = Field(
        description="팀 모집 마감의 원문 정보와 시각·시간대 보완 여부."
    )


class TeamDetail(TeamSummary):
    """팀장 계정과 연결 공고 요약을 포함한 공개 모집글."""

    owner_account_id: UUID = Field(description="팀장 계정의 UUID.")
    contest: ContestSummary = Field(description="연결된 공고의 요약 정보.")
