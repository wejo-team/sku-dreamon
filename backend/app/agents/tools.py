"""서버가 고정한 요청 목적에 맞는 읽기 도구만 모델에 제공한다."""

import asyncio
from typing import Literal
from uuid import UUID

from langchain_core.tools import BaseTool, tool

from app.agents.assessment import assessment_evidence
from app.agents.tool_inputs import (
    ContestFindInput,
    ContestTitleSearchInput,
    PageInput,
    PeopleFindInput,
    PeopleNameSearchInput,
    ResourceDetailInput,
    TeamFindInput,
    TeamNameSearchInput,
)
from app.agents.types import Resource
from app.core.exceptions import AppError
from app.rules.catalogs import FieldCode, RoleCode
from app.rules.contests import RegistrationStatus
from app.services.ai_sources import SourceReader, SourceSearchResult


class ToolBudgetExceeded(Exception):
    """허용된 자료 또는 도구 호출 예산을 초과했다."""


class SourceTools:
    def __init__(
        self, reader: SourceReader, *, max_sources: int, max_calls: int
    ) -> None:
        self.reader = reader
        self.max_sources = max_sources
        self.max_calls = max_calls
        self.calls = 0
        self.observed: dict[str, Resource] = {}
        self._load_lock = asyncio.Lock()

    def count_call(self) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            raise ToolBudgetExceeded()

    async def load(self, kind: str, resource_id: UUID) -> Resource:
        # 짧은 자료 조회를 직렬화해 병렬 도구의 예산 예약 경쟁을 막는다.
        async with self._load_lock:
            key = f"{kind}:{resource_id}"
            if key not in self.observed and len(self.observed) >= self.max_sources:
                raise ToolBudgetExceeded()
            value = await self.reader.get(kind, resource_id)
            # 같은 실행에서 이미 사용한 근거가 변경되면 혼합하지 않는다.
            previous = self.observed.get(key)
            if (
                previous is not None
                and previous.reference.fingerprint != value.reference.fingerprint
            ):
                raise AppError(
                    409,
                    "AI_CONTEXT_CHANGED",
                    "자료가 변경되었습니다. 다시 요청해 주세요.",
                )
            self.observed[key] = value
            return value

    async def items(self, kind: str, ids: list[UUID]) -> list[dict[str, object]]:
        values: list[dict[str, object]] = []
        for resource_id in ids:
            try:
                value = await self.load(kind, resource_id)
            except AppError as error:
                if error.status_code == 404:
                    continue
                raise
            if kind != "application" or value.is_selection_candidate:
                values.append(self.model_input(value))
        return values

    @staticmethod
    def model_input(resource: Resource) -> dict[str, object]:
        value = resource.model_input()
        if resource.reference.kind == "application":
            value["evidence"] = {
                key: evidence.model_dump(mode="json")
                for key, evidence in assessment_evidence(resource).items()
            }
        return value

    async def search_response(
        self, kind: str, result: SourceSearchResult
    ) -> dict[str, object]:
        # 페이지 메타는 도메인 조회 기준이다. 현재 권한으로 제외된 항목 수를
        # 전체 추천 가능 총원으로 해석하지 않도록 totalCount를 제공하지 않는다.
        return {"items": await self.items(kind, result.ids), **result.metadata()}

    def build(self) -> list[BaseTool]:
        if self.reader.context.purpose == "chat":

            @tool(args_schema=PeopleFindInput)
            async def find_people(
                page: int = 1,
                role_code: RoleCode | None = None,
                field_code: FieldCode | None = None,
            ) -> dict[str, object]:
                """공개 프로필을 희망 역할·관심 분야 조건의 AND로 탐색한다.

                이름을 찾을 때는 search_people_by_name을 사용한다. 지원자 권한과
                비공개 정보는 쓰지 않는다. 기술·지역 등 미지원 조건을 추정하지 않는다.
                페이지 메타는 권한 후처리 전 조회 기준이며 전체 추천 가능 수가 아니다.
                """
                self.count_call()
                result = await self.reader.search(
                    "person", page, role_code=role_code, field_code=field_code
                )
                return await self.search_response("person", result)

            @tool(args_schema=PeopleNameSearchInput)
            async def search_people_by_name(
                name: str,
                page: int = 1,
                role_code: RoleCode | None = None,
                field_code: FieldCode | None = None,
            ) -> dict[str, object]:
                """공개 프로필 이름만 리터럴 부분 검색하고 역할·분야를 AND 적용한다.

                소개·기술은 검색하지 않는다. 이름이 아닌 조건 탐색은 find_people.
                공개 권한과 페이지 한도는 find_people과 같다.
                """
                self.count_call()
                result = await self.reader.search(
                    "person",
                    page,
                    name=name,
                    role_code=role_code,
                    field_code=field_code,
                )
                return await self.search_response("person", result)

            @tool(args_schema=ContestFindInput)
            async def find_contests(
                page: int = 1,
                field_code: FieldCode | None = None,
                registration_status: RegistrationStatus | None = None,
                deadline_within_days: int | None = None,
            ) -> dict[str, object]:
                """공모전을 분야·접수 상태·향후 마감 기한의 AND로 탐색한다.

                조건 생략 시 전체 상태를 마감순으로 조회하고 마감 공고는 뒤에 둔다.
                '마감이 가까운'은 이 도구의 마감순을 사용하며 기간이 있으면 일수를 준다.
                제목 검색은 search_contests_by_title. 참가 자격은 원문 확인을 안내한다.
                주최자·지역 등 미지원 조건을 검색했다고 단정하지 않는다.
                """
                self.count_call()
                result = await self.reader.search(
                    "contest",
                    page,
                    field_code=field_code,
                    registration_status=registration_status,
                    deadline_within_days=deadline_within_days,
                )
                return await self.search_response("contest", result)

            @tool(args_schema=ContestTitleSearchInput)
            async def search_contests_by_title(
                title: str,
                page: int = 1,
                field_code: FieldCode | None = None,
                registration_status: RegistrationStatus | None = None,
                deadline_within_days: int | None = None,
            ) -> dict[str, object]:
                """공모전 제목만 리터럴 부분 검색하고 분야·상태·기한을 AND 적용한다.

                주최자·소개·분야 표시명은 텍스트 검색하지 않는다. 이름이 아닌
                '마감 임박' 같은 조건 표현은 title에 넣지 말고 find_contests를 쓴다.
                마감순·페이지 한도·참가 자격 안내는 find_contests와 같다.
                """
                self.count_call()
                result = await self.reader.search(
                    "contest",
                    page,
                    title=title,
                    field_code=field_code,
                    registration_status=registration_status,
                    deadline_within_days=deadline_within_days,
                )
                return await self.search_response("contest", result)

            @tool(args_schema=TeamFindInput)
            async def find_teams(
                page: int = 1,
                role_code: RoleCode | None = None,
            ) -> dict[str, object]:
                """현재 지원 가능한 모집 팀을 모집 역할 코드 조건으로 탐색한다.

                개발자 모집은 role_code='development'. 이름 검색은 search_teams_by_name.
                마감·정원·소속·지원 이력 조건은 해제할 수 없다. 페이지 메타는
                사용자별 지원 가능 여부 후처리 전 기준이며 전체 추천 가능 수가 아니다.
                빈 결과만으로 전체 팀 부재나 마감 때문이라고 단정하지 않는다.
                """
                self.count_call()
                result = await self.reader.search("team", page, role_code=role_code)
                return await self.search_response("team", result)

            @tool(args_schema=TeamNameSearchInput)
            async def search_teams_by_name(
                name: str,
                page: int = 1,
                role_code: RoleCode | None = None,
            ) -> dict[str, object]:
                """팀 이름만 리터럴 부분 검색하고 모집 역할 조건을 AND 적용한다.

                소개·공모전명·역할 표시명은 텍스트 검색하지 않는다.
                조건만이면 find_teams.
                현재 지원 가능 권한·모집 조건·페이지 한도는 find_teams와 같다.
                """
                self.count_call()
                result = await self.reader.search(
                    "team", page, name=name, role_code=role_code
                )
                return await self.search_response("team", result)

            @tool(args_schema=ResourceDetailInput)
            async def get_resource_detail(
                kind: Literal["contest", "team", "person"], resource_id: UUID
            ) -> dict[str, object]:
                """앞선 결과의 실제 식별자로 현재 공개된 상세 근거를 읽는다."""
                self.count_call()
                return (await self.load(kind, resource_id)).model_input()

            return [
                find_people,
                search_people_by_name,
                find_contests,
                search_contests_by_title,
                find_teams,
                search_teams_by_name,
                get_resource_detail,
            ]

        if self.reader.context.application_id is not None:

            @tool
            async def read_applicant() -> dict[str, object]:
                """현재 팀장이 요청한 지원 한 건과 최신 프로필만 읽는다."""
                self.count_call()
                target = self.reader.context.application_id
                assert target is not None
                return self.model_input(await self.load("application", target))

            return [read_applicant]

        @tool(args_schema=PageInput)
        async def list_applicants(
            page: int = 1,
        ) -> dict[str, object]:
            """현재 팀장이 받은 지원 중 지금 새 선발 후보인 지원자를 조회한다."""
            self.count_call()
            result = await self.reader.applicants(page)
            return await self.search_response("application", result)

        return [list_applicants]
