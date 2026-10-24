"""현재 소속의 팀 공간과 팀장 모집 변경에 한정된 전송 계약을 정의한다."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.core.http.schemas import (
    NonnegativeInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
)
from app.rules.catalogs import RoleCode
from app.schemas.profiles import ProfileResponse
from app.schemas.teams import TeamDetail, TeamSummary


class WorkspaceSearch(RequestDTO):
    """현재 소속된 팀 목록의 페이지 조건."""

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


class TeamMember(ResponseDTO):
    """현재 팀원의 소속 정보와 열람 가능한 프로필."""

    membership_id: UUID = Field(description="현재 소속의 UUID.")
    account_id: UUID = Field(description="소속된 계정의 UUID.")
    real_name: str = Field(description="현재 같은 팀 구성원을 식별하는 실명.")
    is_demo: bool = Field(
        description=(
            "계정용 고정 UUID 시드 목록을 기준으로 서버가 판정한 시연용 계정 여부."
        )
    )
    membership_role: Literal["leader", "member"] = Field(
        description=("팀 내 소속 구분. leader는 팀장, member는 팀원입니다.")
    )
    role_code: RoleCode | None = Field(
        description=(
            "선발된 지원 역할 코드. 지원을 통해 생성되지 않은 팀장 소속은 null입니다."
        )
    )
    joined_at: Timestamp = Field(description="현재 소속이 시작된 시각. UTC 기준입니다.")
    profile: ProfileResponse | None = Field(
        description=(
            "조회 권한이 있는 최신 전체 프로필. 일반 팀원이 비공개 "
            "팀원을 조회하면 null입니다."
        )
    )


class TeamSpace(ResponseDTO):
    """현재 소속 관계에 따라 제공하는 팀 공간 정보."""

    team: TeamDetail = Field(description="현재 팀의 상세 정보.")
    members: list[TeamMember] = Field(
        min_length=1, description="팀장을 포함한 현재 구성원 목록. 최소 1명입니다."
    )
    viewer_role: Literal["leader", "member"] = Field(
        description=("현재 조회자의 소속 구분. leader는 팀장, member는 팀원입니다.")
    )
    pending_application_count: NonnegativeInt | None = Field(
        description=(
            "접수·검토 중인 지원 수. 팀장에게만 제공하며 일반 팀원에게는 null입니다."
        )
    )


class WorkspaceTeam(ResponseDTO):
    """본인 워크스페이스의 현재 소속 팀 항목."""

    team: TeamSummary = Field(description="현재 소속된 팀의 요약 정보.")
    membership_id: UUID = Field(description="본인의 현재 소속 UUID.")
    membership_role: Literal["leader", "member"] = Field(
        description=("본인의 소속 구분. leader는 팀장, member는 팀원입니다.")
    )
    role_code: RoleCode | None = Field(
        description="본인이 선발된 역할 코드. 팀장 소속은 null입니다."
    )
    pending_application_count: NonnegativeInt | None = Field(
        description=(
            "접수·검토 중인 지원 수. 팀장에게만 제공하며 일반 팀원에게는 null입니다."
        )
    )
