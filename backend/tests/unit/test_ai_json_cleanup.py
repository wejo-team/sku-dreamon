"""평가 JSON의 연결 종료·전송 실패가 공유 정리 예산 안에서 끝나는지 검사한다."""

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from starlette.types import Message, Scope

from app.routers import ai as router
from app.schemas.ai import AiCompletion
from app.services.ai import StreamCleanup


async def test_json_generation_timeout_does_not_restart_a_hanging_cleanup_budget() -> (
    None
):
    started, closed = asyncio.Event(), asyncio.Event()
    close_calls = 0

    async def results() -> AsyncGenerator[AiCompletion]:
        try:
            started.set()
            await asyncio.Event().wait()
            yield AiCompletion(
                request_id=uuid4(), attempt=1, status="canceled", result=None
            )
        finally:
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()

    async def on_close() -> None:
        nonlocal close_calls
        close_calls += 1
        await asyncio.Event().wait()

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("No request body expected")

    async def send(message: Message) -> None:
        raise AssertionError("Incomplete generation must not publish JSON")

    response = router.AiJsonResponse(
        results(), on_close=on_close, cleanup=StreamCleanup(0.05), timeout_seconds=0.05
    )
    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    before = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(response(scope, receive, send), 0.5)
    assert asyncio.get_running_loop().time() - before < 0.4
    assert started.is_set() and closed.is_set()
    assert close_calls == 1


async def test_json_blocked_send_closes_result_generator_and_runs_cleanup_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(router, "SEND_TIMEOUT_SECONDS", 0.05)
    closed = asyncio.Event()
    close_calls = 0

    async def results() -> AsyncGenerator[AiCompletion]:
        try:
            yield AiCompletion(
                request_id=uuid4(), attempt=1, status="canceled", result=None
            )
        finally:
            closed.set()

    async def on_close() -> None:
        nonlocal close_calls
        close_calls += 1

    async def receive() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("No request body expected")

    async def send(message: Message) -> None:
        await asyncio.Event().wait()

    response = router.AiJsonResponse(
        results(), on_close=on_close, cleanup=StreamCleanup(0.05), timeout_seconds=0.2
    )
    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(response(scope, receive, send), 0.5)
    assert closed.is_set() and close_calls == 1
