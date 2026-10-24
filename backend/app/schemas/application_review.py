"""받은 지원의 팀장 검토용 조회·처리 결과를 정의한다."""

from typing import Annotated

from pydantic import Field

from app.core.http.schemas import RequestDTO, ResponseDTO
from app.schemas.applications import ApplicationResponse, ApplicationStatus
from app.schemas.profiles import ProfileResponse


class ApplicantSearch(RequestDTO):
    """팀장이 받은 지원 목록의 상태 필터와 페이지 조건."""

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


class ApplicantResponse(ResponseDTO):
    """받은 지원과 지원자의 최신 프로필을 묶은 팀장 검토 항목."""

    application: ApplicationResponse = Field(description="팀장이 받은 지원 정보.")
    profile: ProfileResponse = Field(
        description=("해당 지원자의 최신 전체 프로필. 지원 당시의 복사본이 아닙니다.")
    )
    is_selection_candidate: bool = Field(
        description=(
            "지원이 접수·검토 중이고 같은 공모전에 확정 소속이 없는지 "
            "여부. 마감·정원까지 확인한 선발 실행 허가는 아닙니다."
        )
    )
