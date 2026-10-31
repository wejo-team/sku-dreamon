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
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.agents.tools import SourceTools
from app.agents.tracing import AiTraceContext
from app.agents.types import (
    ApplicantAssessmentPlan,
    ApplicantAssessmentSelection,
    AssessmentCriterionPlan,
    PreviousContext,
    RecommendationGate,
    RecommendationPlan,
    Resource,
    Selection,
)
from app.core.config import Settings
from app.main import create_app as create_product_app
from app.schemas.ai import AssessmentKey


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
        trace_context: AiTraceContext | None = None,
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
            # 테스트가 HTTP로 만든 공개 프로필만 지정한다. 임의 결과 ID를 만들지 않는다.
            ids = (
                content.removeprefix("E2E 비교 ").split()
                if content.startswith("E2E 비교 ")
                else [content.rsplit(" ", 1)[-1]]
            )
            resources = [await tools.load("person", UUID(value)) for value in ids]
        elif context.application_id is not None:
            resources = [await tools.load("application", context.application_id)]
        else:
            result = await tools.reader.applicants(1)
            candidates = await tools.items("application", result.ids)
            if not candidates:
                return RecommendationPlan(
                    intent="empty", selections=[], guidance="현재 유효 후보가 없습니다."
                )
            resources = [tools.observed[str(candidates[0]["key"])]]
        return RecommendationPlan(
            intent="recommend",
            selections=[
                Selection(
                    key=resource.reference.key,
                    reason="등록된 관심 분야와 역할을 확인했습니다.",
                    evidence=["현재 서비스에 등록된 자료를 조회했습니다."],
                )
                for resource in resources
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

    async def assess(
        self, tools: SourceTools, *, trace_context: AiTraceContext | None = None
    ) -> ApplicantAssessmentPlan:
        plan = await self.plan(tools, "현재 지원 자료로 검토해 주세요.", [], [])
        resources = [tools.observed[choice.key] for choice in plan.selections]
        remaining_keys: tuple[AssessmentKey, ...] = (
            "skills",
            "experience",
            "availability",
        )
        return ApplicantAssessmentPlan(
            summary="등록된 역할을 확인하고 나머지 사항은 대화로 확인해 주세요.",
            assessments=[
                ApplicantAssessmentSelection(
                    key=resource.reference.key,
                    criteria=[
                        AssessmentCriterionPlan(
                            key="role",
                            score=75,
                            information_status="sufficient",
                            summary="지원 역할이 등록되어 있어요.",
                            evidence_refs=["application.role"],
                        ),
                        *[
                            AssessmentCriterionPlan(
                                key=key,
                                score=None,
                                information_status="insufficient",
                                summary="직접 확인할 정보가 더 필요해요.",
                                evidence_refs=[],
                            )
                            for key in remaining_keys
                        ],
                    ],
                    questions=["이번 프로젝트에서 어떤 역할을 맡고 싶나요?"],
                )
                for resource in resources
            ],
        )


def create_app() -> FastAPI:
    try:
        settings = Settings()
    except ValidationError:
        raise RuntimeError("AI E2E requires valid isolated settings") from None
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
