"""실제 HTTPS E2E에서 모델 driver만 교체하는 명시적 테스트 앱 factory.

제품 설정·라우터·자료 조회·권한·SSE·저장·검증은 그대로 사용한다.
로컬 *_e2e DB와 빈 모델 키를 확인한 뒤에만 앱을 만들며 외부 모델은 쓰지 않는다.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy.engine import make_url

from app.agents.tools import SourceTools
from app.agents.types import (
    PreviousContext,
    RecommendationGate,
    RecommendationPlan,
    Resource,
    Selection,
)
from app.core.config import Settings
from app.main import create_app as create_product_app


class FixtureDriver:
    """조회한 실제 자료만 선택하고 결정론적인 짧은 답변을 스트리밍한다."""

    def __init__(self) -> None:
        self.failed_inputs: set[str] = set()

    async def stream(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: PreviousContext,
        *,
        gate: RecommendationGate,
    ) -> AsyncIterator[str]:
        plan = await self.plan(tools, content, history, await previous())
        await gate(plan)
        resources = [tools.observed[choice.key] for choice in plan.selections]
        async for part in self.write(plan, resources, content):
            yield part

    async def plan(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: list[dict[str, object]],
    ) -> RecommendationPlan:
        if content.startswith("E2E 재시도 ") and content not in self.failed_inputs:
            self.failed_inputs.add(content)
            raise RuntimeError("Synthetic model failure for explicit retry")
        context = tools.reader.context
        tools.count_call()
        if context.purpose == "chat":
            # 테스트가 HTTP로 만든 공개 프로필을 지정한다. 임의 결과 ID를 만들지 않는다.
            resource = await tools.load("person", UUID(content.rsplit(" ", 1)[-1]))
        elif context.application_id is not None:
            resource = await tools.load("application", context.application_id)
        else:
            ids, _ = await tools.reader.applicants(1)
            candidates = await tools.items("application", ids)
            if not candidates:
                return RecommendationPlan(
                    intent="empty", selections=[], guidance="현재 유효 후보가 없습니다."
                )
            resource = tools.observed[str(candidates[0]["key"])]
        return RecommendationPlan(
            intent="recommend",
            selections=[
                Selection(
                    key=resource.reference.key,
                    reason="등록된 관심 분야와 역할을 확인했습니다.",
                    evidence=["현재 서비스에 등록된 자료를 조회했습니다."],
                )
            ],
            guidance="실제 자료와 연결된 테스트 모델 응답입니다.",
        )

    async def write(
        self, plan: RecommendationPlan, resources: list[Resource], content: str
    ) -> AsyncIterator[str]:
        yield "등록된 실제 자료를 확인했습니다. "
        if content.startswith("E2E 중단 "):
            await asyncio.Event().wait()
        await asyncio.sleep(0.2)
        yield "테스트 모델의 연동 검증 응답입니다."


def create_app() -> FastAPI:
    settings = Settings()
    try:
        explicit = make_url(os.environ["DATABASE_URL"])
    except (KeyError, ValueError):
        raise RuntimeError("AI E2E requires an explicit localhost *_e2e DB") from None
    configured = make_url(str(settings.database_url))
    if (
        os.environ.get("E2E_AI_FIXTURE") != "1"
        or explicit != configured
        or explicit.drivername != "postgresql+asyncpg"
        or explicit.host not in {"localhost", "127.0.0.1", "::1"}
        or explicit.query
        or not (explicit.database or "").endswith("_e2e")
        or settings.openai_api_key
    ):
        raise RuntimeError(
            "AI E2E requires opt-in, localhost *_e2e DB and no model key"
        )
    app = create_product_app(settings)
    product_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def fixture_lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with product_lifespan(application):
            original = application.state.ai_driver
            application.state.ai_driver = FixtureDriver()
            try:
                yield
            finally:
                # 제품 종료 전에 원래 값을 복원해 실제 모델 client 정리를 피한다.
                application.state.ai_driver = original

    app.router.lifespan_context = fixture_lifespan
    return app
