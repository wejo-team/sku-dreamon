"""인증된 AI 요청을 실행하고 전송 완료까지 스트림·자원을 정리한다."""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response
from starlette.responses import JSONResponse, StreamingResponse
from starlette.types import Receive, Scope, Send

from app.core.config import Settings
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.dependencies.auth import CurrentSession, get_current_session
from app.dependencies.csrf import require_csrf
from app.schemas.ai import (
    AiCompletion,
    AiPurpose,
    AiRequestView,
    CancelRequest,
    ChatStart,
    ResultValidation,
    RetryStart,
    TargetStart,
    ValidateResult,
)
from app.services.ai import AgentDriver, AiService, StreamCleanup
from app.services.ai_runs import Execution, view

router = APIRouter(
    tags=["AI"],
    dependencies=[Depends(get_current_session), Depends(require_csrf)],
    responses=error_responses(401, 403, 404, 409, 422, 429, 500, 503),
)


def get_ai_service(request: Request) -> AiService:
    return AiService(
        cast(Database, request.app.state.database),
        cast(Settings, request.app.state.settings),
        cast(AgentDriver | None, getattr(request.app.state, "ai_driver", None)),
    )


Service = Annotated[AiService, Depends(get_ai_service)]
logger = logging.getLogger(__name__)
SEND_TIMEOUT_SECONDS = 3
TRANSPORT_ALLOWANCE_SECONDS = 9


class AiStreamResponse(StreamingResponse):
    """한 태스크에서 생성기를 소비해 전송 잠금과 취소 컨텍스트를 보존한다."""

    media_type = "text/event-stream"

    def __init__(
        self,
        events: AsyncGenerator[bytes],
        status_code: int = 200,
        *,
        on_close: Callable[[], Awaitable[None]] | None = None,
        cleanup: StreamCleanup | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.events = events
        self.on_close = on_close
        self.cleanup = cleanup or StreamCleanup()
        self.timeout_seconds = timeout_seconds
        super().__init__(
            events,
            status_code=status_code,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def watch_disconnect() -> None:
            while True:
                if (await receive())["type"] == "http.disconnect":
                    return

        # 반복 취소되는 AnyIO scope 밖의 작업으로 한 번만 취소를 전달한다.
        # 생성기의 finally에서 모델과 DB 세션 정리를 끝낸 뒤 응답을 종료한다.
        streaming = asyncio.create_task(self.stream_response(send))
        disconnected = asyncio.create_task(watch_disconnect())
        try:
            # 헤더·초기 프레임·실패 프레임까지 포함한 응답 전체의 실행 예산.
            async with asyncio.timeout(self.timeout_seconds):
                await asyncio.wait(
                    {streaming, disconnected}, return_when=asyncio.FIRST_COMPLETED
                )
                if streaming.done():
                    await streaming
        finally:
            self.cleanup.start()
            for task in (streaming, disconnected):
                if not task.done():
                    task.cancel()
            try:
                await self.cleanup.run(
                    lambda: asyncio.gather(
                        streaming, disconnected, return_exceptions=True
                    )
                )
                await self.cleanup.run(self.events.aclose)
            except Exception as error:
                logger.warning(
                    "AI transport cleanup deferred: error_type=%s",
                    type(error).__name__,
                )
            finally:
                if self.on_close is not None:
                    # close_stream은 같은 deadline과 이미 시도한 저장을 사용한다.
                    try:
                        await self.cleanup.run(self.on_close)
                    except Exception as error:
                        logger.warning(
                            "AI close callback deferred: error_type=%s",
                            type(error).__name__,
                        )
        if self.background is not None:
            await self.background()

    async def stream_response(self, send: Send) -> None:
        async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
        send_lock = asyncio.Lock()

        async def write(body: bytes) -> None:
            async with send_lock:
                async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
                    await send(
                        {"type": "http.response.body", "body": body, "more_body": True}
                    )

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(10)
                await write(b": keepalive\n\n")

        try:
            async with asyncio.TaskGroup() as tasks:
                pulse = tasks.create_task(heartbeat())
                try:
                    async for chunk in self.events:
                        await write(chunk)
                finally:
                    pulse.cancel()
            async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
        finally:
            try:
                await self.cleanup.run(self.events.aclose)
            except Exception as error:
                logger.warning(
                    "AI generator cleanup deferred: error_type=%s",
                    type(error).__name__,
                )


def stream_response(service: AiService, execution: Execution) -> AiStreamResponse:
    cleanup = StreamCleanup(service.settings.ai_cleanup_timeout_seconds)
    return AiStreamResponse(
        service.stream(execution, cleanup=cleanup),
        on_close=lambda: service.close_stream(execution, cleanup=cleanup),
        cleanup=cleanup,
        timeout_seconds=service.settings.ai_timeout_seconds
        + TRANSPORT_ALLOWANCE_SECONDS,
    )


class AiJsonResponse(JSONResponse):
    """평가 완료 전 연결 종료를 감지하고 현재 권한 잠금 안에서 JSON을 전송한다."""

    media_type = "application/json"

    def __init__(
        self,
        completions: AsyncGenerator[AiCompletion],
        status_code: int = 200,
        *,
        on_close: Callable[[], Awaitable[None]],
        cleanup: StreamCleanup,
        timeout_seconds: float,
    ) -> None:
        self.completions, self.on_close = completions, on_close
        self.cleanup, self.timeout_seconds = cleanup, timeout_seconds
        super().__init__(content=None, status_code=status_code)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def watch_disconnect() -> None:
            while True:
                if (await receive())["type"] == "http.disconnect":
                    return

        async def respond() -> None:
            try:
                async for result in self.completions:
                    response = Response(
                        content=Success(data=result).model_dump_json(),
                        status_code=self.status_code,
                        media_type=self.media_type,
                        headers={"Cache-Control": "no-store"},
                    )
                    async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
                        await response(scope, receive, send)
            finally:
                # publishing의 컨텍스트는 생성기를 소비한 태스크 안에서 닫는다.
                try:
                    await self.cleanup.run(self.completions.aclose)
                except Exception as error:
                    logger.warning(
                        "AI JSON generator cleanup deferred: error_type=%s",
                        type(error).__name__,
                    )

        sending = asyncio.create_task(respond())
        disconnected = asyncio.create_task(watch_disconnect())
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await asyncio.wait(
                    {sending, disconnected}, return_when=asyncio.FIRST_COMPLETED
                )
                if sending.done():
                    await sending
        finally:
            self.cleanup.start()
            for task in (sending, disconnected):
                if not task.done():
                    task.cancel()
            try:
                await self.cleanup.run(
                    lambda: asyncio.gather(
                        sending, disconnected, return_exceptions=True
                    )
                )
                await self.cleanup.run(self.completions.aclose)
            except Exception as error:
                logger.warning(
                    "AI JSON cleanup deferred: error_type=%s", type(error).__name__
                )
            finally:
                try:
                    await self.cleanup.run(self.on_close)
                except Exception as error:
                    logger.warning(
                        "AI JSON close callback deferred: error_type=%s",
                        type(error).__name__,
                    )


def json_response(service: AiService, execution: Execution) -> AiJsonResponse:
    cleanup = StreamCleanup(service.settings.ai_cleanup_timeout_seconds)
    return AiJsonResponse(
        service.complete_applicants(execution, cleanup=cleanup),
        on_close=lambda: service.close_stream(execution, cleanup=cleanup),
        cleanup=cleanup,
        timeout_seconds=service.settings.ai_timeout_seconds
        + TRANSPORT_ALLOWANCE_SECONDS,
    )


@router.post(
    "/ai/chat/stream",
    response_class=AiStreamResponse,
    response_model=None,
    summary="현재 탭 대화의 AI 답변 스트리밍",
)
async def chat(
    payload: ChatStart, principal: CurrentSession, service: Service
) -> AiStreamResponse:
    execution = await service.start(principal, "chat", payload)
    return stream_response(service, execution)


@router.post(
    "/applications/{applicationId}/ai-reviews/stream",
    response_class=AiStreamResponse,
    response_model=None,
    summary="현재 팀장의 기존 지원자 검토 스트리밍",
)
async def review(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    payload: TargetStart,
    principal: CurrentSession,
    service: Service,
) -> AiStreamResponse:
    execution = await service.start(
        principal, "applicant_review", payload, application_id=application_id
    )
    return stream_response(service, execution)


@router.post(
    "/teams/{teamId}/applicant-recommendations/stream",
    response_class=AiStreamResponse,
    response_model=None,
    summary="현재 팀장의 지원자 후보 추천 스트리밍",
)
async def recommend(
    team_id: Annotated[UUID, Path(alias="teamId")],
    payload: TargetStart,
    principal: CurrentSession,
    service: Service,
) -> AiStreamResponse:
    execution = await service.start(
        principal, "applicant_recommendation", payload, team_id=team_id
    )
    return stream_response(service, execution)


@router.post(
    "/applications/{applicationId}/ai-reviews",
    response_class=AiJsonResponse,
    response_model=Success[AiCompletion],
    summary="지원자 구조화 평가를 완성 JSON으로 제공",
)
async def review_json(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    payload: TargetStart,
    principal: CurrentSession,
    service: Service,
) -> AiJsonResponse:
    execution = await service.start(
        principal, "applicant_review", payload, application_id=application_id
    )
    return json_response(service, execution)


@router.post(
    "/teams/{teamId}/applicant-recommendations",
    response_class=AiJsonResponse,
    response_model=Success[AiCompletion],
    summary="유효 지원자 후보의 구조화 평가를 완성 JSON으로 제공",
)
async def recommend_json(
    team_id: Annotated[UUID, Path(alias="teamId")],
    payload: TargetStart,
    principal: CurrentSession,
    service: Service,
) -> AiJsonResponse:
    execution = await service.start(
        principal, "applicant_recommendation", payload, team_id=team_id
    )
    return json_response(service, execution)


@router.post(
    "/ai/requests/{requestId}/retries",
    response_class=AiJsonResponse,
    response_model=Success[AiCompletion],
    summary="실패한 지원자 구조화 평가를 재실행",
)
async def retry_json(
    request_id: Annotated[UUID, Path(alias="requestId")],
    payload: RetryStart,
    principal: CurrentSession,
    service: Service,
) -> AiJsonResponse:
    run = await service.runs.get(principal, request_id)
    if run.purpose == "chat":
        raise AppError(409, "AI_STREAM_REQUIRED", "대화는 스트리밍을 사용해 주세요.")
    if payload.input.request_id != request_id or isinstance(payload.input, ChatStart):
        raise AppError(
            409, "MESSAGE_ID_CONFLICT", "원래 요청과 같은 입력을 보내 주세요."
        )
    execution = await service.start(
        principal,
        cast(AiPurpose, run.purpose),
        payload.input,
        team_id=run.team_id,
        application_id=run.application_id,
        expected_attempt=payload.expected_attempt,
    )
    return json_response(service, execution)


@router.post(
    "/ai/requests/{requestId}/retries/stream",
    response_class=AiStreamResponse,
    response_model=None,
    summary="실패한 현재 시도 재실행",
)
async def retry(
    request_id: Annotated[UUID, Path(alias="requestId")],
    payload: RetryStart,
    principal: CurrentSession,
    service: Service,
) -> AiStreamResponse:
    run = await service.runs.get(principal, request_id)
    if payload.input.request_id != request_id or (run.purpose == "chat") != isinstance(
        payload.input, ChatStart
    ):
        raise AppError(
            409, "MESSAGE_ID_CONFLICT", "원래 요청과 같은 입력을 보내 주세요."
        )
    execution = await service.start(
        principal,
        cast(AiPurpose, run.purpose),
        payload.input,
        team_id=run.team_id,
        application_id=run.application_id,
        expected_attempt=payload.expected_attempt,
    )
    return stream_response(service, execution)


@router.get(
    "/ai/requests/{requestId}",
    response_model=Success[AiRequestView],
    summary="원문 없는 실행 상태 조회",
)
async def status(
    request_id: Annotated[UUID, Path(alias="requestId")],
    response: Response,
    principal: CurrentSession,
    service: Service,
) -> Success[AiRequestView]:
    response.headers["Cache-Control"] = "no-store"
    return Success(data=view(await service.runs.get(principal, request_id)))


@router.put(
    "/ai/requests/{requestId}/cancellation",
    response_model=Success[AiRequestView],
    summary="현재 실행 시도 중단",
)
async def cancel(
    request_id: Annotated[UUID, Path(alias="requestId")],
    payload: CancelRequest,
    response: Response,
    principal: CurrentSession,
    service: Service,
) -> Success[AiRequestView]:
    response.headers["Cache-Control"] = "no-store"
    return Success(
        data=await service.runs.cancel(principal, request_id, payload.expected_attempt)
    )


@router.post(
    "/ai/requests/{requestId}/validation",
    response_model=Success[ResultValidation],
    summary="현재 표시·복사 권한과 결과 무결성 재검증",
)
async def validate_result(
    request_id: Annotated[UUID, Path(alias="requestId")],
    payload: ValidateResult,
    response: Response,
    principal: CurrentSession,
    service: Service,
) -> Success[ResultValidation]:
    response.headers["Cache-Control"] = "no-store"
    return Success(data=await service.validate_result(principal, request_id, payload))
