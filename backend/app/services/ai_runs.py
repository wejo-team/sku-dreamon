"""AI 실행의 공유 소유권·멱등성·재시도·취소와 전송 시 권한을 관리한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import AgentContext, Reference, Resource, fingerprint
from app.core.config import Settings
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.models.ai_runs import AiRun
from app.repositories import ai_runs as repository
from app.repositories.recruitment_locks import lock_accounts
from app.schemas.ai import (
    AiFailure,
    AiPurpose,
    AiRequestView,
    AiStatus,
    ChatStart,
    TargetStart,
)
from app.services import ai_chat
from app.services.ai_sources import SourceReader
from app.services.sessions import IDLE_LIFETIME, SessionPrincipal


class RunCanceled(Exception):
    """현재 실행이 중단되거나 새 시도로 대체되었다."""


class ContextChanged(Exception):
    """공개 범위 또는 실행에 사용한 근거가 달라졌다."""


@dataclass(frozen=True)
class Execution:
    request_id: UUID
    attempt: int
    context: AgentContext
    input: ChatStart | TargetStart


_FAILURES = {
    "temporary_failure": ("답변을 준비하지 못했습니다. 다시 시도해 주세요.", True),
    "invalid_output": ("답변의 근거를 확인하지 못했습니다. 다시 시도해 주세요.", True),
    "context_changed": (
        "정보나 접근 권한이 변경되었습니다. 새로 요청해 주세요.",
        False,
    ),
    "limit_exceeded": (
        "요청 처리 한도에 도달했습니다. 조건을 줄여 새로 요청해 주세요.",
        False,
    ),
}


def failure(code: str, attempt: int) -> AiFailure:
    message, retryable = _FAILURES[code]
    return AiFailure.model_validate(
        {"code": code, "message": message, "retryable": retryable and attempt < 3}
    )


def view(run: AiRun) -> AiRequestView:
    return AiRequestView(
        id=run.ai_run_id,
        purpose=cast(AiPurpose, run.purpose),
        conversation_id=run.conversation_id,
        team_id=run.team_id,
        application_id=run.application_id,
        attempt=run.attempt,
        status=cast(AiStatus, run.status),
        failure=None
        if run.failure_code is None
        else failure(run.failure_code, run.attempt),
        expires_at=run.expires_at,
    )


def references(run: AiRun) -> list[Reference]:
    return TypeAdapter(list[Reference]).validate_python(run.references)


class RunService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    @staticmethod
    def require_owner(run: AiRun | None, principal: SessionPrincipal) -> AiRun:
        if (
            run is None
            or run.account_id != principal.account_id
            or run.auth_session_id != principal.auth_session_id
            or run.expires_at <= datetime.now(UTC)
        ):
            raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
        return run

    async def clean_expired(self) -> None:
        async with self.database.session() as session:
            await repository.expire_runs(session, datetime.now(UTC))
            await session.commit()

    async def resolve_context(
        self,
        principal: SessionPrincipal,
        purpose: AiPurpose,
        *,
        team_id: UUID | None = None,
        application_id: UUID | None = None,
    ) -> AgentContext:
        context = AgentContext(principal, purpose, team_id, application_id)
        reader = SourceReader(self.database, context)
        await reader.require_session()
        if application_id is not None:
            resource = await reader.get("application", application_id)
            context = AgentContext(
                principal, purpose, resource.reference.team_id, application_id
            )
        elif purpose == "applicant_recommendation":
            await reader.applicants(1)
        return context

    async def prepare(
        self,
        context: AgentContext,
        payload: ChatStart | TargetStart,
        *,
        expected_attempt: int | None = None,
    ) -> Execution:
        await self.clean_expired()
        principal = context.principal
        conversation_id = (
            payload.conversation_id if isinstance(payload, ChatStart) else None
        )
        client_message_id = (
            payload.client_message_id if isinstance(payload, ChatStart) else None
        )
        scope_id = conversation_id or context.application_id or context.team_id
        scope = f"{context.purpose}:{scope_id}"
        digest = fingerprint(
            {
                "purpose": context.purpose,
                "team": str(context.team_id),
                "application": str(context.application_id),
                "input": payload.model_dump(mode="json"),
            }
        )
        async with self.database.session() as session:
            await lock_accounts(session, [principal.account_id])
            now = datetime.now(UTC)
            run = await repository.get_run(session, payload.request_id, lock=True)
            if run is not None:
                self.require_owner(run, principal)
                if run.request_fingerprint != digest:
                    raise AppError(
                        409,
                        "MESSAGE_ID_CONFLICT",
                        "동일 요청 ID에 다른 내용을 사용할 수 없습니다.",
                    )
                if expected_attempt is None:
                    code = (
                        "REQUEST_ALREADY_RUNNING"
                        if run.status == "pending"
                        else "REQUEST_ALREADY_FINISHED"
                    )
                    raise AppError(
                        409,
                        code,
                        "이미 접수한 요청입니다. 현재 실행 상태를 확인해 주세요.",
                    )
                if run.attempt != expected_attempt:
                    raise AppError(
                        409, "ATTEMPT_CONFLICT", "현재 처리 시도가 변경되었습니다."
                    )
                if (
                    run.status != "failed"
                    or run.failure_code is None
                    or not failure(run.failure_code, run.attempt).retryable
                ):
                    raise AppError(
                        409, "REQUEST_NOT_RETRYABLE", "새 요청으로 다시 시도해 주세요."
                    )
            elif expected_attempt is not None:
                raise AppError(
                    404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다."
                )
            elif conversation_id is not None and client_message_id is not None:
                if (
                    await repository.find_message(
                        session,
                        principal.auth_session_id,
                        conversation_id,
                        client_message_id,
                    )
                    is not None
                ):
                    raise AppError(
                        409,
                        "MESSAGE_ID_CONFLICT",
                        "같은 메시지의 기존 요청 ID를 사용해 주세요.",
                    )
            if await repository.pending_count(session, principal.account_id, scope):
                raise AppError(
                    409, "REQUEST_ALREADY_RUNNING", "이 요청의 응답이 진행 중입니다."
                )
            if (
                await repository.pending_count(session, principal.account_id)
                >= self.settings.ai_concurrent_requests
                or await repository.recent_count(
                    session, principal.account_id, now - timedelta(hours=1)
                )
                >= self.settings.ai_requests_per_hour
            ):
                raise AppError(
                    429,
                    "RATE_LIMITED",
                    "요청이 많습니다. 잠시 후 다시 시도해 주세요.",
                    {"Retry-After": "60"},
                )
            if isinstance(payload, ChatStart):
                await ai_chat.save_user(
                    session,
                    principal.account_id,
                    payload,
                    now,
                    retry=expected_attempt is not None,
                )
            if run is None:
                run = AiRun(
                    ai_run_id=payload.request_id,
                    account_id=principal.account_id,
                    auth_session_id=principal.auth_session_id,
                    purpose=context.purpose,
                    scope_key=scope,
                    conversation_id=conversation_id,
                    client_message_id=client_message_id,
                    team_id=context.team_id,
                    application_id=context.application_id,
                    request_fingerprint=digest,
                    attempt=1,
                    created_at=now,
                )
                repository.add_run(session, run)
            else:
                run.attempt += 1
            run.status = "pending"
            run.failure_code = None
            run.references = []
            run.selected_keys = []
            run.result_hash = None
            run.updated_at = now
            run.deadline_at = now + timedelta(seconds=self.settings.ai_timeout_seconds)
            run.expires_at = now + timedelta(seconds=self.settings.ai_retention_seconds)
            await session.commit()
            return Execution(run.ai_run_id, run.attempt, context, payload)

    async def get(self, principal: SessionPrincipal, request_id: UUID) -> AiRun:
        async with self.database.session() as session:
            run = self.require_owner(
                await repository.get_run(session, request_id, lock=True), principal
            )
            if run.status == "pending" and run.deadline_at <= datetime.now(UTC):
                run.status, run.failure_code = "failed", "temporary_failure"
                run.updated_at = datetime.now(UTC)
                await session.commit()
        try:
            await self.resolve_context(
                principal,
                cast(AiPurpose, run.purpose),
                team_id=run.team_id,
                application_id=run.application_id,
            )
        except AppError as error:
            if error.status_code in (403, 404):
                raise AppError(
                    404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다."
                ) from None
            raise
        return run

    async def ensure_active(self, execution: Execution) -> None:
        await SourceReader(self.database, execution.context).require_session()
        async with self.database.session() as session:
            run = self.require_owner(
                await repository.get_run(session, execution.request_id),
                execution.context.principal,
            )
            if run.attempt != execution.attempt or run.status == "canceled":
                raise RunCanceled()
            if run.status == "failed":
                raise TimeoutError()
            if run.status != "pending":
                raise RunCanceled()
            if run.deadline_at <= datetime.now(UTC):
                raise TimeoutError()

    async def cancel(
        self, principal: SessionPrincipal, request_id: UUID, expected_attempt: int
    ) -> AiRequestView:
        await self.get(principal, request_id)
        async with self.database.session() as session:
            run = self.require_owner(
                await repository.get_run(session, request_id, lock=True), principal
            )
            if run.attempt != expected_attempt:
                raise AppError(
                    409, "ATTEMPT_CONFLICT", "현재 처리 시도가 변경되었습니다."
                )
            if run.status == "pending":
                run.status = "canceled"
                run.updated_at = datetime.now(UTC)
                await session.commit()
            return view(run)

    async def finish(
        self,
        execution: Execution,
        *,
        status: AiStatus,
        failure_code: str | None = None,
        sources: list[Reference] | None = None,
        selected_keys: list[str] | None = None,
        result_hash: str | None = None,
    ) -> bool:
        async with self.database.session() as session:
            run = await repository.get_run(session, execution.request_id, lock=True)
            if (
                run is None
                or run.attempt != execution.attempt
                or run.status != "pending"
            ):
                return False
            run.status, run.failure_code = status, failure_code
            run.result_hash = result_hash
            run.references = [ref.model_dump(mode="json") for ref in sources or []]
            run.selected_keys = selected_keys or []
            run.updated_at = datetime.now(UTC)
            await session.commit()
            return True

    async def complete(
        self,
        execution: Execution,
        *,
        status: Literal["succeeded", "empty"],
        sources: list[Reference],
        selected_keys: list[str],
        result_hash: str,
        answer: str,
    ) -> None:
        """현재 권한 검사·완성 답변 저장·실행 완료를 하나의 트랜잭션으로 확정한다."""
        async with self.database.session() as session:
            run, _ = await self._publication(session, execution, sources)
            now = datetime.now(UTC)
            if isinstance(execution.input, ChatStart):
                await ai_chat.save_answer(
                    session,
                    execution.input,
                    answer,
                    execution.attempt,
                    self.settings.ai_model,
                    sources,
                    now,
                )
            run.status, run.failure_code = status, None
            run.result_hash = result_hash
            run.references = [ref.model_dump(mode="json") for ref in sources]
            run.selected_keys = selected_keys
            run.updated_at = now
            await session.commit()

    @asynccontextmanager
    async def publishing(
        self,
        execution: Execution,
        sources: list[Reference],
        *,
        completed: bool = False,
        allow_stale: bool = False,
    ) -> AsyncIterator[list[Resource]]:
        """짧은 ASGI 전송 동안 자료 변경과 세션 회수를 직렬화한다."""
        async with self.database.session() as session:
            _, values = await self._publication(
                session,
                execution,
                sources,
                completed=completed,
                allow_stale=allow_stale,
            )
            yield values

    async def _publication(
        self,
        session: AsyncSession,
        execution: Execution,
        sources: list[Reference],
        *,
        completed: bool = False,
        allow_stale: bool = False,
    ) -> tuple[AiRun, list[Resource]]:
        principal = execution.context.principal
        await repository.lock_publication_sources(
            session,
            account_ids=sorted(
                {
                    principal.account_id,
                    *(ref.account_id for ref in sources if ref.account_id),
                }
            ),
            contest_ids=sorted({ref.contest_id for ref in sources if ref.contest_id}),
            team_ids=sorted({ref.team_id for ref in sources if ref.team_id}),
            application_ids=sorted(
                {ref.resource_id for ref in sources if ref.kind == "application"}
            ),
            profile_ids=sorted({ref.account_id for ref in sources if ref.account_id}),
        )
        run = self.require_owner(
            await repository.get_run(session, execution.request_id, lock=True),
            principal,
        )
        allowed = ("succeeded", "empty") if completed else ("pending",)
        if run.attempt != execution.attempt or run.status not in allowed:
            raise RunCanceled()
        login = await repository.session_record(
            session, principal.auth_session_id, lock=True
        )
        now = datetime.now(UTC)
        if not completed and now >= run.deadline_at:
            raise TimeoutError()
        if (
            login is None
            or login.account_id != principal.account_id
            or login.revoked_at is not None
            or now >= login.expires_at
            or now >= login.last_seen_at + IDLE_LIFETIME
        ):
            raise ContextChanged()
        reader = SourceReader(self.database, execution.context)
        values: list[Resource] = []
        for source in sources:
            try:
                current = await reader.get(source.kind, source.resource_id)
            except AppError as error:
                if error.status_code in (401, 403, 404, 409):
                    raise ContextChanged() from None
                raise
            if allow_stale and source.kind == "application":
                if (
                    execution.context.purpose == "applicant_recommendation"
                    and source.key in run.selected_keys
                    and not current.is_selection_candidate
                ):
                    raise ContextChanged()
            elif current.reference.fingerprint != source.fingerprint:
                raise ContextChanged()
            values.append(current)
        return run, values
