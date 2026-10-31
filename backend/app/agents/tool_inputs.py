"""모델이 사용하는 조회 인자와 카탈로그 코드의 의미를 명시한다."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.rules.catalogs import CatalogCode, FieldCode, RoleCode
from app.rules.contests import RegistrationStatus


def _choices(catalog: type[CatalogCode]) -> str:
    return ", ".join(f"{item.value}={item.display_name}" for item in catalog)


class ToolInput(BaseModel):
    """지원하지 않는 조건을 조용히 무시하지 않는 도구 입력."""

    model_config = ConfigDict(extra="forbid")


class PageInput(ToolInput):
    page: int = Field(
        default=1,
        ge=1,
        le=10,
        strict=True,
        description="1부터 시작하는 페이지. hasMore=true이면 다음 페이지를 조회한다.",
    )


class SearchInput(PageInput):
    query: str = Field(
        default="",
        max_length=100,
        description=(
            "이 도구의 enum 인자로 표현한 조건을 제외한 자유 검색어. 명시된 "
            "텍스트에서 부분 일치로 검색하며 필터와 AND로 적용한다. 모든 조건을 "
            "지원하는 enum으로 전달했다면 빈 문자열을 사용한다. 지원하지 않는 "
            "조건은 생략하지 말고 조회된 사실로 확인하거나 사용자에게 질문한다."
        ),
    )


class TeamSearchInput(SearchInput):
    role_code: RoleCode | None = Field(
        default=None,
        description=(
            "모집 역할 코드. 생략/null은 역할 제한 없음. "
            f"{_choices(RoleCode)}. 개발자 모집은 development와 query=''를 사용한다."
        ),
    )


class PeopleSearchInput(SearchInput):
    role_code: RoleCode | None = Field(
        default=None,
        description=f"희망 역할 코드. 생략/null은 제한 없음. {_choices(RoleCode)}.",
    )
    field_code: FieldCode | None = Field(
        default=None,
        description=f"관심 분야 코드. 생략/null은 제한 없음. {_choices(FieldCode)}.",
    )


class ContestSearchInput(SearchInput):
    field_code: FieldCode | None = Field(
        default=None,
        description=f"공모전 분야 코드. 생략/null은 제한 없음. {_choices(FieldCode)}.",
    )
    registration_status: RegistrationStatus | None = Field(
        default=None,
        description=(
            "접수 상태. scheduled=접수 예정, open=접수 중, closed=접수 마감. "
            "생략/null은 모든 접수 상태를 조회한다."
        ),
    )


class ResourceDetailInput(ToolInput):
    kind: Literal["contest", "team", "person"] = Field(
        description="contest=공모전, team=팀, person=공개 사람. 앞선 결과의 종류."
    )
    resource_id: UUID = Field(description="앞선 조회 결과에서 얻은 실제 자료 UUID.")
