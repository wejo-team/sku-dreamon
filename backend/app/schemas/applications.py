"""지원의 공개 응답과 명시적인 상태 변경 요청을 정의한다."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.core.http.schemas import RequestDTO, ResponseDTO, Timestamp, Version
from app.rules.catalogs import RoleCode
from app.schemas.teams import TeamSummary


class ApplicationStatus(StrEnum):
    """지원의 접수·검토·선발·종결 상태."""

    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    SELECTED = "selected"
    REJECTED = "rejected"
    CANCELED = "canceled"
    DISCARDED = "discarded"


class ApplicationResponse(ResponseDTO):
    """조회 관계에 맞게 폐기 원인을 제한한 지원 정보."""

    id: UUID = Field(
        description=("지원 시도의 UUID. 신규 지원과 재지원마다 별도의 ID를 사용합니다.")
    )
    version: Version = Field(
        description="현재 지원 버전. 양의 정수를 나타내는 십진 문자열입니다."
    )
    team_id: UUID = Field(description="지원한 팀의 UUID.")
    contest_id: UUID = Field(description="지원한 공고의 UUID.")
    applicant_account_id: UUID = Field(description="지원자 계정의 UUID.")
    role_code: RoleCode = Field(description="지원한 역할 코드.")
    message: str | None = Field(
        description=("지원 시 작성한 선택 메시지. 메시지가 없으면 null입니다.")
    )
    status: ApplicationStatus = Field(
        description=(
            "현재 지원 상태. submitted는 접수, "
            "reviewing은 검토, selected는 선발, "
            "rejected는 미선발, canceled는 취소, "
            "discarded는 폐기입니다."
        )
    )
    discard_reason: Literal["selected_elsewhere", "team_created_elsewhere"] | None = (
        Field(
            description=(
                "폐기 사유. selected_elsewhere는 다른 팀 "
                "선발, team_created_elsewhere는 본인 팀 "
                "생성이며 폐기 상태가 아니면 null입니다."
            )
        )
    )
    discarded_by_application_id: UUID | None = Field(
        description=(
            "다른 팀 선발로 폐기된 경우 원인 지원 UUID. 열람 "
            "가능한 본인에게만 제공하며 받은 팀장에게는 null입니다."
        )
    )
    discarded_by_team_id: UUID | None = Field(
        description=(
            "본인 팀 생성으로 폐기된 경우 원인 팀 UUID. "
            "본인에게만 제공하며 받은 팀장에게는 null입니다."
        )
    )
    submitted_at: Timestamp = Field(
        description="해당 지원 시도의 최초 접수 시각. UTC 기준입니다."
    )
    updated_at: Timestamp = Field(
        description="지원을 마지막으로 변경한 시각. UTC 기준입니다."
    )


class VersionedAction(RequestDTO):
    """조회한 지원 버전을 지정하는 상태 변경 요청."""

    expected_version: Version = Field(
        description=(
            "클라이언트가 조회한 지원 버전의 십진 문자열. 현재 버전과 "
            "다르면 변경을 거부합니다."
        )
    )


class CancellationResult(ResponseDTO):
    """본인 지원 취소 결과와 소속 종료 여부."""

    application: ApplicationResponse = Field(
        description="취소 처리 결과가 반영된 본인 지원 정보."
    )
    membership_ended: bool = Field(
        description=(
            "선발 후 취소로 소속을 종료했는지 여부. 이미 취소된 "
            "요청은 기존 결과를 유지합니다."
        )
    )


class MyApplication(ResponseDTO):
    """본인 지원 현황과 지원한 팀의 요약."""

    application: ApplicationResponse = Field(description="본인의 해당 지원 시도 정보.")
    team: TeamSummary = Field(description="지원한 팀의 현재 요약 정보.")
    is_current_member: bool = Field(
        description="조회 시점에 본인이 해당 팀의 현재 구성원인지 여부."
    )


class ApplicationSearch(RequestDTO):
    """본인 지원 목록의 상태 필터와 페이지 조건."""

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
    status: ApplicationStatus | None = Field(
        default=None, description="조회할 지원 상태. 생략 시 모든 상태를 조회합니다."
    )
