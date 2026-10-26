"""인증된 AI 요청을 실행하고 전송 완료까지 스트림·자원을 정리한다."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.core.config import Settings
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.core.http.handlers import error_responses
from app.core.http.schemas import Success
from app.dependencies.auth import CurrentSession, get_current_session
from app.dependencies.csrf import require_csrf
from app.schemas.ai import (
    AiPurpose,
    AiRequestView,
    CancelRequest,
    ChatStart,
    ResultValidation,
    RetryStart,
    TargetStart,
    ValidateResult,
)
from app.services.ai import AgentDriver, AiService
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


class AiStreamResponse(StreamingResponse):
    """한 태스크에서 생성기를 소비해 전송 잠금과 취소 컨텍스트를 보존한다."""

    media_type = "text/event-stream"

    def __init__(
        self,
        events: AsyncGenerator[bytes],
        status_code: int = 200,
        *,
        on_close: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.events = events
        self.on_close = on_close
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
            await asyncio.wait(
                {streaming, disconnected}, return_when=asyncio.FIRST_COMPLETED
            )
            if streaming.done():
                await streaming
        finally:
            for task in (streaming, disconnected):
                if not task.done():
                    task.cancel()
            await asyncio.gather(streaming, disconnected, return_exceptions=True)
            await self.events.aclose()
            if self.on_close is not None:
                await self.on_close()
        if self.background is not None:
            await self.background()

    async def stream_response(self, send: Send) -> None:
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
                await asyncio.wait_for(
                    send(
                        {"type": "http.response.body", "body": body, "more_body": True}
                    ),
                    timeout=3,
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
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            await self.events.aclose()


def stream_response(service: AiService, execution: Execution) -> AiStreamResponse:
    return AiStreamResponse(
        service.stream(execution), on_close=lambda: service.close_stream(execution)
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
