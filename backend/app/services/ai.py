"""검증된 조회 근거로 AI 답변을 만들고 현재 권한을 적용해 스트리밍한다."""

import asyncio
import hmac
import logging
import time
from collections.abc import AsyncGenerator, Awaitable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.agents.factory import AgentDriver as AgentDriver
from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.types import RecommendationPlan, Reference, Resource, fingerprint
from app.core.config import Settings
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.schemas.ai import (
    AiEvent,
    AiPurpose,
    AiResult,
    ApplicantRecommendation,
    ApplicantRecommendationResult,
    ApplicantReviewResult,
    ChatResult,
    ChatStart,
    ProfileVersion,
    ResourceCard,
    ResultValidation,
    TargetStart,
    ValidateResult,
)
from app.services.ai_runs import (
    ContextChanged,
    Execution,
    RunCanceled,
    RunService,
    failure,
    references,
)
from app.services.ai_sources import SourceReader
from app.services.sessions import SessionPrincipal

logger = logging.getLogger(__name__)


def validate_plan(plan: RecommendationPlan, sources: SourceTools) -> list[Resource]:
    purpose = sources.reader.context.purpose
    keys = [choice.key for choice in plan.selections]
    if len(set(keys)) != len(keys) or any(key not in sources.observed for key in keys):
        raise ValueError("Unverified recommendation IDs")
    selected = [sources.observed[key] for key in keys]
    if purpose == "chat" and (
        len(keys) > 3
        or any(value.reference.kind == "application" for value in selected)
    ):
        raise ValueError("Invalid public selection")
    if purpose == "applicant_review" and (
        len(selected) != 1
        or selected[0].reference.resource_id != sources.reader.context.application_id
    ):
        raise ValueError("Missing requested applicant")
    if purpose == "applicant_recommendation" and any(
        not value.is_selection_candidate for value in selected
    ):
        raise ContextChanged()
    if plan.intent == "recommend" and not selected:
        raise ValueError("Missing recommendation")
    if plan.intent != "recommend" and selected:
        raise ValueError("Unexpected recommendation")
    return selected


def profile_version(resource: Resource) -> ProfileVersion:
    reference = resource.reference
    if reference.account_id is None or reference.profile_version is None:
        raise ValueError("Missing profile version")
    return ProfileVersion(
        account_id=reference.account_id,
        used_version=reference.profile_version,
        current_version=reference.profile_version,
    )


def build_result(
    execution: Execution, plan: RecommendationPlan, selected: list[Resource], text: str
) -> AiResult:
    now = datetime.now(UTC)
    if execution.context.purpose == "chat":
        cards = [
            ResourceCard(
                kind=cast("LiteralCardKind", resource.reference.kind),
                resource_id=resource.reference.resource_id,
                title=resource.title,
                reason=choice.reason,
                field_codes=resource.field_codes,
                role_codes=resource.role_codes,
                is_demo=resource.is_demo,
            )
            for choice, resource in zip(plan.selections, selected, strict=True)
        ]
        return ChatResult(answer=text, cards=cards, generated_at=now)
    if execution.context.purpose == "applicant_review":
        resource = selected[0]
        return ApplicantReviewResult(
            application_id=resource.reference.resource_id,
            summary=text,
            evidence=plan.selections[0].evidence,
            profile_versions=[profile_version(resource)],
            is_stale=False,
            is_selection_candidate=resource.is_selection_candidate,
            generated_at=now,
        )
    return ApplicantRecommendationResult(
        summary=text,
        candidates=[
            ApplicantRecommendation(
                application_id=resource.reference.resource_id,
                reason=choice.reason,
                profile_version=profile_version(resource),
            )
            for choice, resource in zip(plan.selections, selected, strict=True)
        ],
        is_stale=False,
        generated_at=now,
    )


# 카드 종류는 도구 자료 종류보다 좁으며 application은 일반 카드에 포함하지 않는다.

LiteralCardKind = Literal["contest", "team", "person"]


class AiService:
    def __init__(
        self, database: Database, settings: Settings, driver: AgentDriver | None
    ) -> None:
        self.database, self.settings, self.driver = database, settings, driver
        self.runs = RunService(database, settings)

    def require_driver(self) -> AgentDriver:
        if self.driver is None:
            raise AppError(
                503,
                "AI_NOT_CONFIGURED",
                "AI 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            )
        return self.driver

    async def start(
        self,
        principal: SessionPrincipal,
        purpose: AiPurpose,
        payload: ChatStart | TargetStart,
        *,
        team_id: UUID | None = None,
        application_id: UUID | None = None,
        expected_attempt: int | None = None,
    ) -> Execution:
        self.require_driver()
        context = await self.runs.resolve_context(
            principal, purpose, team_id=team_id, application_id=application_id
        )
        try:
            return await self.runs.prepare(
                context, payload, expected_attempt=expected_attempt
            )
        except SQLAlchemyError as error:
            # SQL 인자의 대화 원문을 서버 traceback에 남기지 않는다.
            logger.warning(
                "AI request storage failed: request_id=%s error_type=%s",
                payload.request_id,
                type(error).__name__,
            )
            raise AppError(
                503,
                "TEMPORARY_UNAVAILABLE",
                "요청을 저장하지 못했습니다. 다시 시도해 주세요.",
            ) from None

    async def _await_active[T](
        self, execution: Execution, operation: Awaitable[T]
    ) -> T:
        task = asyncio.ensure_future(operation)
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.5)
                await self.runs.ensure_active(execution)
            return task.result()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def previous_context(
        self, execution: Execution, sources: SourceTools
    ) -> list[dict[str, object]]:
        if not isinstance(execution.input, ChatStart):
            return []
        values: list[dict[str, object]] = []
        for previous in execution.input.previous_results:
            run = await self.runs.get(execution.context.principal, previous.request_id)
            if (
                run.purpose != "chat"
                or run.conversation_id != execution.input.conversation_id
                or run.attempt != previous.attempt
                or run.status not in ("succeeded", "empty")
            ):
                raise ContextChanged()
            for ref in references(run):
                if ref.key not in run.selected_keys:
                    continue
                try:
                    current = await sources.load(ref.kind, ref.resource_id)
                except AppError as error:
                    if error.status_code == 404:
                        # 현재 열람 가능한 자료만 대화 맥락에 다시 넣는다.
                        continue
                    raise
                values.append(current.model_input())
        return values

    async def stream(self, execution: Execution) -> AsyncGenerator[bytes]:
        sequence = 0
        terminal = False
        started_at = time.monotonic()
        last_event = "disconnected"

        def event(name: str, **payload: object) -> bytes:
            nonlocal sequence, last_event
            sequence += 1
            last_event = name
            return AiEvent.model_validate(
                {
                    "event": name,
                    "requestId": execution.request_id,
                    "attempt": execution.attempt,
                    "sequence": sequence,
                    **payload,
                }
            ).to_sse()

        try:
            yield event("started", purpose=execution.context.purpose)
            yield event("progress", stage="searching")
            async with asyncio.timeout(self.settings.ai_timeout_seconds):
                sources = SourceTools(
                    SourceReader(self.database, execution.context),
                    max_sources=self.settings.ai_max_sources,
                    max_calls=self.settings.ai_max_tool_calls,
                )

                async def previous() -> list[dict[str, object]]:
                    return await self.previous_context(execution, sources)

                content = (
                    execution.input.content
                    if isinstance(execution.input, ChatStart)
                    else "현재 지원 자료로 검토해 주세요."
                )
                history = (
                    execution.input.history
                    if isinstance(execution.input, ChatStart)
                    else []
                )
                driver = self.require_driver()
                plan: RecommendationPlan | None = None
                selected: list[Resource] = []
                refs: list[Reference] = []

                async def gate(proposed: RecommendationPlan) -> None:
                    nonlocal plan, selected, refs
                    if plan is not None:
                        raise ValueError("Recommendation already prepared")
                    approved = proposed.model_copy(deep=True)
                    candidates = validate_plan(approved, sources)
                    current_refs = [
                        resource.reference.model_copy(deep=True)
                        for resource in sources.observed.values()
                    ]
                    async with self.runs.publishing(execution, current_refs):
                        pass
                    # 이후 모델·도구가 제안 객체를 바꿔도 게시할 후보는 고정한다.
                    selected = [item.model_copy(deep=True) for item in candidates]
                    refs = current_refs
                    plan = approved

                text = ""
                answering = False
                response = driver.stream(sources, content, history, previous, gate=gate)
                try:
                    while True:
                        try:
                            delta = await self._await_active(execution, anext(response))
                        except StopAsyncIteration:
                            break
                        if plan is None:
                            raise ValueError("Answer before recommendation validation")
                        if not answering:
                            yield event("progress", stage="validating")
                            yield event("progress", stage="writing")
                            answering = True
                        text += delta
                        if len(text) > 12000:
                            raise ToolBudgetExceeded()
                        async with self.runs.publishing(execution, refs):
                            yield event("answer.delta", text=delta)
                finally:
                    close = getattr(response, "aclose", None)
                    if close is not None:
                        await close()
                if plan is None or not text.strip():
                    raise ValueError("Empty model answer")
                result = build_result(execution, plan, selected, text)
                status: Literal["empty", "succeeded"] = (
                    "empty" if plan.intent == "empty" else "succeeded"
                )
                await self.runs.complete(
                    execution,
                    status=status,
                    sources=refs,
                    selected_keys=[item.key for item in plan.selections],
                    result_hash=fingerprint(result.model_dump(mode="json")),
                    answer=text,
                )
                async with self.runs.publishing(execution, refs, completed=True):
                    # 완료는 커밋됐지만 클라이언트의 수신 성공까지 보장하지 않는다.
                    yield event("result", result=result.model_dump(mode="json"))
                    yield event("done", status=status)
                terminal = True
        except RunCanceled:
            yield event("canceled")
            terminal = True
        except (ContextChanged, AppError) as error:
            if isinstance(error, AppError) and error.status_code not in (
                401,
                403,
                404,
                409,
            ):
                await self.runs.finish(
                    execution, status="failed", failure_code="temporary_failure"
                )
                yield event(
                    "error",
                    failure=failure("temporary_failure", execution.attempt).model_dump(
                        mode="json"
                    ),
                )
            else:
                await self.runs.finish(
                    execution, status="failed", failure_code="context_changed"
                )
                yield event("invalidated", reason="context_changed")
            terminal = True
        except TimeoutError:
            await self.runs.finish(
                execution, status="failed", failure_code="temporary_failure"
            )
            yield event(
                "error",
                failure=failure("temporary_failure", execution.attempt).model_dump(
                    mode="json"
                ),
            )
            terminal = True
        except ToolBudgetExceeded:
            await self.runs.finish(
                execution, status="failed", failure_code="limit_exceeded"
            )
            yield event(
                "error",
                failure=failure("limit_exceeded", execution.attempt).model_dump(
                    mode="json"
                ),
            )
            terminal = True
        except Exception as error:
            code = (
                "invalid_output"
                if isinstance(error, ValueError)
                else "temporary_failure"
            )
            # 제공자 예외 문자열에는 입력·인증값이 포함될 수 있어 종류만 기록한다.
            logger.warning(
                "AI request failed: request_id=%s error_type=%s",
                execution.request_id,
                type(error).__name__,
            )
            with suppress(Exception):
                await self.runs.finish(execution, status="failed", failure_code=code)
            yield event(
                "error",
                failure=failure(code, execution.attempt).model_dump(mode="json"),
            )
            terminal = True
        finally:
            logger.info(
                "AI execution request_id=%s attempt=%s purpose=%s "
                "event=%s elapsed_ms=%s",
                execution.request_id,
                execution.attempt,
                execution.context.purpose,
                last_event,
                round((time.monotonic() - started_at) * 1000),
            )
            if not terminal:
                with suppress(Exception):
                    await self.runs.finish(execution, status="canceled")

    async def close_stream(self, execution: Execution) -> None:
        try:
            async with asyncio.timeout(5):
                await self.runs.finish(execution, status="canceled")
        except Exception as error:
            logger.warning(
                "AI cleanup deferred: request_id=%s error_type=%s",
                execution.request_id,
                type(error).__name__,
            )

    async def validate_result(
        self, principal: SessionPrincipal, request_id: UUID, payload: ValidateResult
    ) -> ResultValidation:
        run = await self.runs.get(principal, request_id)
        digest = fingerprint(payload.result.model_dump(mode="json"))
        if (
            run.attempt != payload.attempt
            or run.result_hash is None
            or not hmac.compare_digest(digest, run.result_hash)
        ):
            raise AppError(
                409,
                "AI_RESULT_MISMATCH",
                "결과를 확인할 수 없습니다. 새로 요청해 주세요.",
            )
        context = await self.runs.resolve_context(
            principal,
            cast(AiPurpose, run.purpose),
            team_id=run.team_id,
            application_id=run.application_id,
        )
        execution = Execution(
            request_id,
            run.attempt,
            context,
            TargetStart.model_validate({"requestId": request_id}),
        )
        try:
            async with self.runs.publishing(
                execution, references(run), completed=True, allow_stale=True
            ) as current:
                result = payload.result.model_copy(deep=True)
                by_id = {item.reference.resource_id: item for item in current}
                if isinstance(result, ApplicantReviewResult):
                    actual = by_id[result.application_id]
                    result.profile_versions[0].current_version = (
                        actual.reference.profile_version or "1"
                    )
                    result.is_stale = (
                        result.profile_versions[0].used_version
                        != result.profile_versions[0].current_version
                    )
                    result.is_selection_candidate = actual.is_selection_candidate
                elif isinstance(result, ApplicantRecommendationResult):
                    for candidate in result.candidates:
                        candidate.profile_version.current_version = (
                            by_id[candidate.application_id].reference.profile_version
                            or "1"
                        )
                    result.is_stale = any(
                        item.profile_version.used_version
                        != item.profile_version.current_version
                        for item in result.candidates
                    )
                return ResultValidation(valid=True, result=result)
        except (ContextChanged, RunCanceled):
            return ResultValidation(valid=False, result=None)
