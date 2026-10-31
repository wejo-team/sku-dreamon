"""모델이 사용하는 조회 인자와 카탈로그 코드의 의미를 명시한다."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.rules.catalogs import CatalogCode, FieldCode, RoleCode
from app.rules.contests import RegistrationStatus


def _choices(catalog: type[CatalogCode]) -> str:
    return ", ".join(f"{item.value}={item.display_name}" for item in catalog)


def _valid_search_text(value: str) -> str:
    if "\x00" in value:
        raise ValueError("검색어에 사용할 수 없는 문자가 있습니다.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("검색어에 사용할 수 없는 문자가 있습니다.") from error
    return value


LiteralSearchText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_valid_search_text),
]


class ToolInput(BaseModel):
    """지원하지 않는 조건을 조용히 무시하지 않는 도구 입력."""

    model_config = ConfigDict(extra="forbid")


class PageInput(ToolInput):
    page: int = Field(
        default=1,
        ge=1,
        le=10,
        strict=True,
        description=(
            "1~10의 페이지. 기본 1. 예: hasMore=true이면 반환된 page+1을 조회한다. "
            "pageLimitReached=true이면 조회 한도에 도달했으므로 조건을 좁힌다."
        ),
    )


class TeamFindInput(PageInput):
    role_code: RoleCode | None = Field(
        default=None,
        description=(
            "모집 역할 코드. 생략/null은 역할 제한 없음. 다른 조건과 AND. "
            f"{_choices(RoleCode)}. 예: 개발자 모집은 development. "
            "기술·지역 필터는 지원하지 않으며 미지원 인자는 거부한다."
        ),
    )


class PeopleFindInput(PageInput):
    role_code: RoleCode | None = Field(
        default=None,
        description=(
            "희망 역할 코드. 생략/null은 역할 제한 없음. 다른 조건과 AND. "
            f"{_choices(RoleCode)}. 예: 개발 역할은 development. "
            "보유 기술 조건과 구분하며 skill_code 등 미지원 인자는 거부한다."
        ),
    )
    field_code: FieldCode | None = Field(
        default=None,
        description=(
            "관심 분야 코드. 생략/null은 분야 제한 없음. 다른 조건과 AND. "
            f"{_choices(FieldCode)}. 예: IT 관심 분야는 it_technology."
        ),
    )


class ContestFindInput(PageInput):
    field_code: FieldCode | None = Field(
        default=None,
        description=(
            "공모전 분야 코드. 생략/null은 분야 제한 없음. 다른 조건과 AND. "
            f"{_choices(FieldCode)}. 예: IT 공모전은 it_technology. "
            "주최자·지역·참가 자격 필터는 지원하지 않으며 미지원 인자는 거부한다."
        ),
    )
    registration_status: RegistrationStatus | None = Field(
        default=None,
        description=(
            "접수 상태 코드. scheduled=접수 예정, open=접수 중, closed=접수 마감. "
            "생략/null은 모든 상태. 다른 조건과 AND. 예: 접수 중은 open. "
            "closed와 deadline_within_days는 모순이므로 함께 사용할 수 없다."
        ),
    )
    deadline_within_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        strict=True,
        description=(
            "서버 조회 시각부터 N×24시간 이내 마감하는 공모전. 정수 1~365, "
            "생략/null은 기한 제한 없음. 예: 7은 향후 7×24시간. "
            "현재 시각 < 마감 <= 현재 시각+N일이며 다른 조건과 AND. "
            "closed와 함께 사용할 수 없다. 달력의 이번 주·오늘과는 다르다. "
            "appliedFilters의 checkedAt/deadlineAfter/deadlineOnOrBefore를 확인한다."
        ),
    )

    @model_validator(mode="after")
    def reject_closed_deadline_window(self) -> Self:
        if (
            self.registration_status == RegistrationStatus.CLOSED
            and self.deadline_within_days is not None
        ):
            raise ValueError(
                "접수 마감(closed)과 미래 마감 기한(deadline_within_days)은 "
                "함께 사용할 수 없습니다."
            )
        return self


class ContestTitleSearchInput(ContestFindInput):
    title: LiteralSearchText = Field(
        description=(
            "공모전 제목의 필수 리터럴 부분 검색어. 앞뒤 공백 제거 후 1~100자. "
            "예: 'AI'. %와 _도 일반 문자로 찾는다. 주최자·소개·분야는 "
            "검색하지 않으며 다른 조건과 AND. 기한·분야 조건만이면 find_contests."
        )
    )


class TeamNameSearchInput(TeamFindInput):
    name: LiteralSearchText = Field(
        description=(
            "팀 이름의 필수 리터럴 부분 검색어. 앞뒤 공백 제거 후 1~100자. "
            "예: 'Alpha'. %와 _도 일반 문자로 찾는다. 소개·공모전명·역할은 "
            "검색하지 않으며 다른 조건과 AND. 역할 조건만이면 find_teams."
        )
    )


class PeopleNameSearchInput(PeopleFindInput):
    name: LiteralSearchText = Field(
        description=(
            "공개 프로필 이름의 필수 리터럴 부분 검색어. 앞뒤 공백 제거 후 1~100자. "
            "예: '김'. %와 _도 일반 문자로 찾는다. 소개·역할·기술은 "
            "검색하지 않으며 다른 조건과 AND. 역할·분야 조건만이면 find_people."
        )
    )


class ResourceDetailInput(ToolInput):
    kind: Literal["contest", "team", "person"] = Field(
        description="contest=공모전, team=팀, person=공개 사람. 앞선 결과의 종류."
    )
    resource_id: UUID = Field(description="앞선 조회 결과에서 얻은 실제 자료 UUID.")
