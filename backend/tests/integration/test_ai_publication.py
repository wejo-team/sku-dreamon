"""AI 전송·재검증이 작은 연결 풀에서도 현재 권한을 유지하며 완료되는지 검사한다."""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.tools import SourceTools
from app.agents.types import RecommendationPlan, Selection
from app.core.db.base import Base
from app.core.db.session import Database
from app.models.contests import ContestAudience
from app.schemas.ai import ChatStart, TargetStart, ValidateResult
from app.services.ai import AiService
from tests.integration.application_review_support import review_data  # noqa: F401 -- fixture
from tests.integration.application_support import (
    ApplicationData,
    application_data,  # noqa: F401 -- fixture
)
from tests.integration.test_ai import (
    FakeDriver,
    ai_data,  # noqa: F401 -- fixture
    events,
    payload,
    principal,
    settings,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]
SourceKind = Literal["person", "contest", "team", "application"]


class PublicationDriver(FakeDriver):
    def __init__(self, data: ApplicationData, kind: SourceKind) -> None:
        super().__init__(data)
        self.kind = kind

    async def plan(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: list[dict[str, object]],
    ) -> RecommendationPlan:
        if self.kind in ("person", "application"):
            return await super().plan(tools, content, history, previous)
        identifier = (
            self.data.contest_id if self.kind == "contest" else self.data.other_team_id
        )
        resource = await tools.load(self.kind, identifier)
        return RecommendationPlan(
            intent="recommend",
            selections=[
                Selection(
                    key=resource.reference.key, reason="현재 등록 자료", evidence=[]
                )
            ],
            guidance="현재 자료를 확인하세요.",
        )


@pytest.fixture
async def single_connection_database(
    ai_data: ApplicationData,  # noqa: F811 -- pytest 의존 fixture
    database_url: str,
) -> AsyncIterator[Database]:
    # 기존 fixture의 스키마만 사용하며 원래 fixture 엔진은 준비·정리를 맡는다.
    async with ai_data.database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, [Base.metadata.tables["contest_audiences"]]
            )
        )
    async with ai_data.database.session() as session:
        session.add(
            ContestAudience(contest_id=ai_data.contest_id, audience_code="student")
        )
        await session.commit()
    engine = create_async_engine(
        database_url,
        execution_options=dict(ai_data.database.engine.get_execution_options()),
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
    )
    try:
        yield Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()


@pytest.mark.parametrize("kind", ["person", "contest", "team", "application"])
async def test_stream_and_concurrent_validation_with_one_connection(
    ai_data: ApplicationData,  # noqa: F811 -- pytest 의존 fixture
    single_connection_database: Database,
    kind: SourceKind,
) -> None:
    data = ai_data
    service = AiService(
        single_connection_database, settings(), PublicationDriver(data, kind)
    )
    identity = principal(
        data, data.leader_id if kind == "application" else data.applicant_id
    )
    if kind == "application":
        execution = await service.start(
            identity,
            "applicant_review",
            TargetStart.model_validate({"requestId": payload()["requestId"]}),
            application_id=data.application_id,
        )
    else:
        execution = await service.start(
            identity, "chat", ChatStart.model_validate(payload())
        )
    chunks = [chunk async for chunk in service.stream(execution)]
    stream = events(b"".join(chunks).decode())
    assert stream[-1]["event"] == "done", stream
    result = next(item["result"] for item in stream if item["event"] == "result")
    validation = ValidateResult.model_validate({"attempt": 1, "result": result})

    assert (
        await service.validate_result(identity, execution.request_id, validation)
    ).valid
    results = await asyncio.gather(
        *(
            service.validate_result(identity, execution.request_id, validation)
            for _ in range(5)
        )
    )
    assert all(value.valid and value.result == validation.result for value in results)
