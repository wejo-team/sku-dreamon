"""외부 모델·DB 없이 SSE 종료의 공유 예산과 실패 경계를 검증한다."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Self, cast
from uuid import uuid4

import pytest
from starlette.types import Message, Scope

from app.agents.tools import SourceTools
from app.agents.tracing import AiTraceContext
from app.agents.types import (
    AgentContext,
    PreviousContext,
    RecommendationGate,
    RecommendationPlan,
    Reference,
    Resource,
)
from app.core.config import Settings
from app.core.db.session import Database
from app.routers import ai as ai_router
from app.routers.ai import stream_response
from app.schemas.ai import AiStatus, ChatStart
from app.services.ai import AiService
from app.services.ai_runs import Execution, RunService
from app.services.sessions import SessionPrincipal


class Runs:
    def __init__(self, *, finish_delay: float | None = 0) -> None:
        self.finish_delay = finish_delay
        self.finishes: list[tuple[AiStatus, str | None]] = []
        self.finish_closed = asyncio.Event()
        self.completed = False

    async def ensure_active(self, execution: Execution) -> None:
        pass

    @asynccontextmanager
    async def publishing(
        self, execution: Execution, sources: list[Reference], *, completed: bool = False
    ) -> AsyncIterator[list[Resource]]:
        yield []

    async def finish(
        self, execution: Execution, *, status: AiStatus, failure_code: str | None = None
    ) -> bool:
        self.finishes.append((status, failure_code))
        try:
            if self.finish_delay is None:
                await asyncio.Event().wait()
            else:
                await asyncio.sleep(self.finish_delay)
            return True
        finally:
            self.finish_closed.set()

    async def complete(self, execution: Execution, **kwargs: object) -> None:
        self.completed = True


class Driver:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.entered = asyncio.Event()
        self.closed = asyncio.Event()

    def stream(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: PreviousContext,
        *,
        gate: RecommendationGate,
        trace_context: AiTraceContext | None = None,
    ) -> AsyncIterator[str]:
        return Output(self, gate)


class Output:
    def __init__(self, driver: Driver, gate: RecommendationGate) -> None:
        self.driver, self.gate = driver, gate
        self.sent = False

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> str:
        driver = self.driver
        driver.entered.set()
        if self.sent:
            raise StopAsyncIteration
        if driver.mode.startswith("error"):
            raise RuntimeError("fake provider failure")
        await self.gate(RecommendationPlan(intent="empty", selections=[], guidance=""))
        if driver.mode == "blocked":
            await asyncio.Event().wait()
        self.sent = True
        return "답변"

    async def aclose(self) -> None:
        try:
            if self.driver.mode == "close_hangs":
                await asyncio.Event().wait()
            elif self.driver.mode.endswith("close_slow"):
                await asyncio.sleep(0.07)
        finally:
            self.driver.closed.set()


def setup(
    mode: str, *, finish_delay: float | None = 0
) -> tuple[AiService, Execution, Driver, Runs]:
    settings = Settings(ai_cleanup_timeout_seconds=0.1, _env_file=None)
    driver, runs = Driver(mode), Runs(finish_delay=finish_delay)
    service = AiService(cast(Database, None), settings, driver)
    service.runs = cast(RunService, runs)
    identity = SessionPrincipal(
        uuid4(), uuid4(), b"unused", datetime.now(UTC) + timedelta(hours=1)
    )
    payload = ChatStart.model_validate(
        {
            "requestId": uuid4(),
            "conversationId": uuid4(),
            "clientMessageId": uuid4(),
            "content": "질문",
        }
    )
    execution = Execution(
        payload.request_id, 1, AgentContext(identity, "chat"), payload
    )
    return service, execution, driver, runs


async def within_budget[T](operation: Awaitable[T]) -> T:
    """회귀 전의 무한 정리를 테스트 프로세스에 남기지 않고 실패시킨다."""
    task = asyncio.ensure_future(operation)
    try:
        done, _ = await asyncio.wait({task}, timeout=0.4)
        assert task in done, "stream cleanup exceeded its total budget"
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.wait({task}, timeout=0.2)
        if task.done() and not task.cancelled():
            task.exception()


async def collect(service: AiService, execution: Execution) -> list[dict[str, object]]:
    frames = [chunk async for chunk in service.stream(execution)]
    return [
        {
            "event": chunk.decode().split("\n", 1)[0][7:],
            **json.loads(chunk.decode().split("data: ", 1)[1]),
        }
        for chunk in frames
    ]


async def test_failed_finish_is_bounded_once_and_remains_an_error() -> None:
    service, execution, driver, runs = setup("error", finish_delay=None)
    result = await within_budget(collect(service, execution))
    assert result[-1]["event"] == "error"
    assert not runs.completed
    assert runs.finishes == [("failed", "temporary_failure")]
    assert driver.closed.is_set() and runs.finish_closed.is_set()


async def test_slow_provider_close_cannot_commit_a_success() -> None:
    service, execution, driver, runs = setup("close_hangs")
    result = await within_budget(collect(service, execution))
    assert result[-1]["event"] == "error"
    assert not any(frame["event"] in ("result", "done") for frame in result)
    assert not runs.completed
    assert driver.closed.is_set()


async def test_generator_close_preserves_exit_when_provider_cleanup_times_out() -> None:
    service, execution, driver, runs = setup("close_hangs")
    stream = service.stream(execution)
    while b"event: answer.delta" not in await anext(stream):
        pass
    await within_budget(stream.aclose())
    assert driver.closed.is_set()
    assert not runs.completed
    assert await anext(stream, None) is None


async def test_external_response_cancellation_propagates_and_reaps_producer() -> None:
    service, execution, driver, runs = setup("blocked", finish_delay=None)
    response = stream_response(service, execution)

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        pass

    tasks = asyncio.all_tasks()
    pending = asyncio.create_task(response({"type": "http"}, receive, send))
    await driver.entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await within_budget(pending)
    assert driver.closed.is_set() and runs.finish_closed.is_set()
    assert not (asyncio.all_tasks() - tasks)


async def test_provider_finish_and_on_close_share_one_deadline() -> None:
    service, execution, driver, runs = setup("error_close_slow", finish_delay=None)
    response = stream_response(service, execution)
    sent: list[Message] = []

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        sent.append(message)

    before = asyncio.get_running_loop().time()
    tasks = asyncio.all_tasks()
    await within_budget(response({"type": "http"}, receive, send))
    elapsed = asyncio.get_running_loop().time() - before
    assert 0.09 <= elapsed < 0.16, elapsed
    assert runs.finishes == [("failed", "temporary_failure")]
    assert driver.closed.is_set() and runs.finish_closed.is_set()
    assert not (asyncio.all_tasks() - tasks)
    assert any(b"event: error" in message.get("body", b"") for message in sent)


async def test_generic_close_callback_uses_response_budget() -> None:
    service, execution, _, _ = setup("answer")
    response = stream_response(service, execution)
    callback_closed = asyncio.Event()

    async def on_close() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            callback_closed.set()

    response.on_close = on_close

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        pass

    await within_budget(response({"type": "http"}, receive, send))
    assert callback_closed.is_set()


@pytest.mark.parametrize("phase", ["headers", "body", "last_body"])
async def test_every_transport_send_has_a_finite_limit(
    phase: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ai_router, "SEND_TIMEOUT_SECONDS", 0.04)
    service, execution, _, _ = setup("answer")
    response = stream_response(service, execution)
    send_closed = asyncio.Event()

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        if (
            phase == "headers"
            and message["type"] == "http.response.start"
            or phase == "body"
            and b"answer.delta" in message.get("body", b"")
            or phase == "last_body"
            and message.get("more_body") is False
        ):
            try:
                await asyncio.Event().wait()
            finally:
                send_closed.set()

    tasks = asyncio.all_tasks()
    with pytest.raises((TimeoutError, ExceptionGroup)):
        await within_budget(response({"type": "http"}, receive, send))
    assert send_closed.is_set()
    assert not (asyncio.all_tasks() - tasks)


async def test_response_runtime_limit_cancels_generation_and_reaps_tasks() -> None:
    service, execution, driver, runs = setup("blocked", finish_delay=None)
    response = stream_response(service, execution)
    response.timeout_seconds = 0.04

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        pass

    tasks = asyncio.all_tasks()
    with pytest.raises(TimeoutError):
        await within_budget(response({"type": "http"}, receive, send))
    assert driver.closed.is_set() and runs.finish_closed.is_set()
    assert runs.finishes == [("canceled", None)]
    assert not (asyncio.all_tasks() - tasks)


@pytest.mark.parametrize("failure", ["disconnect", "headers", "body", "last_body"])
async def test_transport_shutdown_reaps_producer_and_bounds_finalization(
    failure: str,
) -> None:
    service, execution, driver, runs = setup(
        "blocked" if failure == "disconnect" else "answer", finish_delay=None
    )
    response = stream_response(service, execution)
    sent: list[Message] = []

    async def receive() -> Message:
        if failure == "disconnect":
            await driver.entered.wait()
            return {"type": "http.disconnect"}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        sent.append(message)
        if (
            failure == "headers"
            and message["type"] == "http.response.start"
            or failure == "body"
            and b"answer.delta" in message.get("body", b"")
            or failure == "last_body"
            and message.get("more_body") is False
        ):
            raise OSError("fake closed transport")

    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    task_set = asyncio.all_tasks()
    if failure in ("headers", "body", "last_body"):
        with pytest.raises((OSError, ExceptionGroup)):
            await within_budget(response(scope, receive, send))
    else:
        await within_budget(response(scope, receive, send))
    assert not (asyncio.all_tasks() - task_set), "producer/heartbeat outlived response"
    if failure in ("disconnect", "body"):
        assert driver.closed.is_set()
    if failure != "last_body":
        assert runs.finishes == [("canceled", None)]
        assert runs.finish_closed.is_set()
    assert not any(message.get("more_body") is False for message in sent[:-1])
