"""서버가 고정한 요청 목적에 맞는 읽기 도구만 모델에 제공한다."""

import asyncio
from typing import Annotated, Literal
from uuid import UUID

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from app.agents.types import Resource
from app.core.exceptions import AppError
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

            @tool
            async def search_resources(
                kind: Literal["contest", "team", "person"],
                query: Annotated[str, Field(max_length=100)] = "",
                page: Annotated[int, Field(ge=1, le=10)] = 1,
            ) -> dict[str, object]:
                """공개 자료를 핵심 단어로 검색하고 없으면 빈 검색어로 확인한다."""
                self.count_call()
                ids, more = await self.reader.search(kind, query, page)
                return {"items": await self.items(kind, ids), "hasMore": more}

            @tool
            async def read_resource(
                kind: Literal["contest", "team", "person"], resource_id: UUID
            ) -> dict[str, object]:
                """앞선 결과의 실제 식별자로 현재 공개된 상세 근거를 읽는다."""
                self.count_call()
                return (await self.load(kind, resource_id)).model_input()

            return [search_resources, read_resource]

        if self.reader.context.application_id is not None:

            @tool
            async def read_applicant() -> dict[str, object]:
                """현재 팀장이 요청한 지원 한 건과 최신 프로필만 읽는다."""
                self.count_call()
                target = self.reader.context.application_id
                assert target is not None
                return (await self.load("application", target)).model_input()

            return [read_applicant]

        @tool
        async def list_applicants(
            page: Annotated[int, Field(ge=1, le=10)] = 1,
        ) -> dict[str, object]:
            """현재 팀장이 받은 지원 중 지금 새 선발 후보인 지원자를 조회한다."""
            self.count_call()
            ids, more = await self.reader.applicants(page)
            return {"items": await self.items("application", ids), "hasMore": more}

        return [list_applicants]
