"""서버가 고정한 요청 목적에 맞는 읽기 도구만 모델에 제공한다."""

import asyncio
from typing import Literal
from uuid import UUID

from langchain_core.tools import BaseTool, tool

from app.agents.tool_inputs import (
    ContestSearchInput,
    PageInput,
    PeopleSearchInput,
    ResourceDetailInput,
    TeamSearchInput,
)
from app.agents.types import Resource
from app.core.exceptions import AppError
from app.rules.catalogs import FieldCode, RoleCode
from app.rules.contests import RegistrationStatus
from app.services.ai_sources import SourceReader


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
                values.append(value.model_input())
        return values

    def build(self) -> list[BaseTool]:
        if self.reader.context.purpose == "chat":

            @tool(args_schema=PeopleSearchInput)
            async def search_people(
                query: str = "",
                page: int = 1,
                role_code: RoleCode | None = None,
                field_code: FieldCode | None = None,
            ) -> dict[str, object]:
                """공개 프로필을 역할·분야 enum과 이름·소개·표시명 검색어로 찾는다.

                조건은 AND로 결합한다. 지원자 권한·본인 비공개 정보는 쓰지 않는다.
                """
                self.count_call()
                ids, more = await self.reader.search(
                    "person", query, page, role_code=role_code, field_code=field_code
                )
                return {"items": await self.items("person", ids), "hasMore": more}

            @tool(args_schema=ContestSearchInput)
            async def search_contests(
                query: str = "",
                page: int = 1,
                field_code: FieldCode | None = None,
                registration_status: RegistrationStatus | None = None,
            ) -> dict[str, object]:
                """공모전을 분야·접수 상태 enum과 제목·주최자·분야 검색어로 찾는다.

                조건은 AND로 결합하며 마감순으로 조회한다. 자격은 원문 확인을 안내한다.
                """
                self.count_call()
                ids, more = await self.reader.search(
                    "contest",
                    query,
                    page,
                    field_code=field_code,
                    registration_status=registration_status,
                )
                return {"items": await self.items("contest", ids), "hasMore": more}

            @tool(args_schema=TeamSearchInput)
            async def search_teams(
                query: str = "",
                page: int = 1,
                role_code: RoleCode | None = None,
            ) -> dict[str, object]:
                """현재 지원 가능한 팀을 모집 역할 enum과 팀명·소개·공모전명으로 찾는다.

                개발자 모집은 role_code='development', query=''로 검색한다.
                조건은 AND로 결합한다. 마감·정원·소속·지원 이력 조건은 해제할 수 없다.
                빈 결과만으로 전체 팀 부재나 마감 때문이라고 단정하지 않는다.
                """
                self.count_call()
                ids, more = await self.reader.search(
                    "team", query, page, role_code=role_code
                )
                return {"items": await self.items("team", ids), "hasMore": more}

            @tool(args_schema=ResourceDetailInput)
            async def get_resource_detail(
                kind: Literal["contest", "team", "person"], resource_id: UUID
            ) -> dict[str, object]:
                """앞선 결과의 실제 식별자로 현재 공개된 상세 근거를 읽는다."""
                self.count_call()
                return (await self.load(kind, resource_id)).model_input()

            return [search_people, search_contests, search_teams, get_resource_detail]

        if self.reader.context.application_id is not None:

            @tool
            async def read_applicant() -> dict[str, object]:
                """현재 팀장이 요청한 지원 한 건과 최신 프로필만 읽는다."""
                self.count_call()
                target = self.reader.context.application_id
                assert target is not None
                return (await self.load("application", target)).model_input()

            return [read_applicant]

        @tool(args_schema=PageInput)
        async def list_applicants(
            page: int = 1,
        ) -> dict[str, object]:
            """현재 팀장이 받은 지원 중 지금 새 선발 후보인 지원자를 조회한다."""
            self.count_call()
            ids, more = await self.reader.applicants(page)
            return {"items": await self.items("application", ids), "hasMore": more}

        return [list_applicants]
