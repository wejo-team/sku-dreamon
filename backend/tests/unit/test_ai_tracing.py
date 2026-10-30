"""LangSmith 추적의 명시적 설정·비밀 보호·비차단 수명을 검증한다."""

import asyncio
import json
import threading
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import requests
from langchain_core.messages import AIMessageChunk
from langsmith import Client, get_tracing_context, tracing_context
from pydantic import SecretStr, ValidationError

from app.agents import factory, tracing
from app.agents.factory import OpenAiAgentDriver
from app.agents.tools import SourceTools
from app.agents.tracing import TRACE_QUEUE_SIZE, AiTraceContext, AiTracing
from app.core.config import Settings
from app.services.ai_sources import SourceReader
from tests.unit.test_ai_runtime import Script, ScriptedModel, prepare


def test_tracing_requires_an_explicit_key_and_defaults_off() -> None:
    config = Settings(_env_file=None)
    assert config.langsmith_tracing is False
    with pytest.raises(ValidationError, match="LangSmith"):
        Settings(langsmith_tracing=True, _env_file=None)
    config = Settings(
        langsmith_tracing=True,
        langsmith_api_key=SecretStr("synthetic-tracing-key"),
        langsmith_workspace_id=uuid4(),
        _env_file=None,
    )
    assert "synthetic-tracing-key" not in repr(config)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://api.smith.langchain.com",
        "https://user:secret@example.com",
        "https://example.com?key=secret",
        "https://example.com#secret",
    ],
)
def test_tracing_endpoint_requires_https_without_credentials(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        Settings(langsmith_endpoint=endpoint, _env_file=None)


def test_tracing_rejects_blank_project_and_key() -> None:
    with pytest.raises(ValidationError):
        Settings(langsmith_project="   ", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(
            langsmith_tracing=True,
            langsmith_api_key=SecretStr("  "),
            _env_file=None,
        )


def enabled_settings() -> Settings:
    return Settings(
        langsmith_tracing=True,
        langsmith_api_key=SecretStr("synthetic-tracing-key"),
        langsmith_project="test-traces",
        langsmith_workspace_id=uuid4(),
        _env_file=None,
    )


def sources(purpose: str = "applicant_recommendation") -> SourceTools:
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose=purpose)
    return SourceTools(reader, max_sources=30, max_calls=8)


def driver(
    monkeypatch: pytest.MonkeyPatch, script: Script, settings: Settings
) -> OpenAiAgentDriver:
    model = ScriptedModel(script=script)
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **kwargs: model)
    return OpenAiAgentDriver(settings)


async def test_disabled_ignores_ambient_native_tracing_across_iterator_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    native = Mock(side_effect=AssertionError("native tracer must stay disabled"))
    monkeypatch.setattr(
        "langchain_core.tracers.langchain.LangChainTracer.__init__", native
    )
    sdk = Mock(side_effect=AssertionError("disabled client must not be created"))
    monkeypatch.setattr(tracing, "Client", sdk)
    runtime = driver(
        monkeypatch,
        Script(
            rounds=[
                [prepare()],
                [AIMessageChunk(content="first"), AIMessageChunk(content="second")],
            ]
        ),
        Settings(langsmith_tracing=False, _env_file=None),
    )
    stream = runtime.stream(
        sources(), "private request", [], AsyncMock(return_value=[]), gate=AsyncMock()
    )

    async def next_in_ambient_context() -> str:
        with tracing_context(enabled=True, metadata={"private": "ambient identity"}):
            value = await anext(stream)
            assert get_tracing_context()["enabled"] is True
            return value

    assert await asyncio.create_task(next_in_ambient_context()) == "first"
    assert await asyncio.create_task(next_in_ambient_context()) == "second"
    with pytest.raises(StopAsyncIteration):
        await asyncio.create_task(next_in_ambient_context())
    sdk.assert_not_called()
    native.assert_not_called()


async def test_real_sdk_serialization_exports_only_allowlisted_spans(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    bodies: list[bytes] = []
    main_thread = threading.get_ident()

    def capture(
        self: requests.Session, method: str, url: str, **kwargs: Any
    ) -> requests.Response:
        assert threading.get_ident() != main_thread
        assert method in {"POST", "PATCH"}
        assert url.startswith("https://api.smith.langchain.com/runs")
        assert kwargs["timeout"] == (1, 1)
        bodies.append(kwargs["data"])
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.url = url
        return response

    monkeypatch.setattr(requests.Session, "request", capture)

    def client(**kwargs: Any) -> Client:
        return Client(**kwargs)

    monkeypatch.setattr(tracing, "Client", client)
    monkeypatch.setenv("LANGCHAIN_REVISION_ID", "private-environment-metadata")
    private_id = uuid4()
    sentinel = f"private-input-{private_id}"
    script = Script(
        rounds=[
            [AIMessageChunk(content='{"reason":"allowed"}')],
            [prepare()],
            [
                AIMessageChunk(
                    content="private answer",
                    usage_metadata={
                        "input_tokens": 7,
                        "output_tokens": 3,
                        "total_tokens": 10,
                    },
                )
            ],
        ]
    )
    runtime = driver(monkeypatch, script, enabled_settings())
    tools = sources("chat")
    caplog.set_level("INFO", logger="app.agents.tracing")
    try:
        assert [
            part
            async for part in runtime.stream(
                tools,
                sentinel,
                ["private history"],
                AsyncMock(return_value=[{"identity": sentinel}]),
                gate=AsyncMock(),
                trace_context=AiTraceContext(private_id, 2),
            )
        ] == ["private answer"]
    finally:
        await runtime.tracing.aclose()
    assert bodies
    raw = b"\n".join(bodies).decode()
    for forbidden in (
        sentinel,
        str(private_id),
        "private answer",
        "private history",
        "synthetic-tracing-key",
        "private-environment-metadata",
        "serialized",
        "messages",
    ):
        assert forbidden not in raw
    updates = [json.loads(body) for body in bodies]
    runs = [run for run in updates if run.get("name")]
    assert {run["name"] for run in runs} == {
        "ai_turn",
        "input_guard",
        "react_model",
        "final_answer",
        "prepare_recommendations",
    }
    root = next(run for run in runs if run["name"] == "ai_turn")
    assert all(run["trace_id"] == root["id"] for run in runs)
    assert all(run.get("parent_run_id") == root["id"] for run in runs if run != root)
    assert all(run["inputs"] == {} for run in runs)
    model_ids = {run["id"] for run in runs if run["run_type"] == "llm"}
    assert all(
        run["extra"]["metadata"].get("ls_model_name") == "gpt-6-luna"
        and run["extra"]["metadata"].get("ls_provider") == "openai"
        for run in updates
        if run["id"] in model_ids
    )
    assert any(
        run.get("extra", {}).get("metadata", {}).get("usage_metadata")
        == {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
        for run in updates
    )
    assert str(private_id) in caplog.text and root["id"] in caplog.text


async def test_failed_export_and_close_never_fail_a_model_stream(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = Mock(spec=Client)
    client.create_run.side_effect = RuntimeError("private exporter exception")
    client.update_run.side_effect = RuntimeError("private exporter exception")
    client.close.side_effect = RuntimeError("private exporter exception")
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    runtime = driver(
        monkeypatch,
        Script(rounds=[[prepare()], [AIMessageChunk(content="answer")]]),
        enabled_settings(),
    )
    assert [
        part
        async for part in runtime.stream(
            sources(), "request", [], AsyncMock(return_value=[]), gate=AsyncMock()
        )
    ] == ["answer"]
    await runtime.tracing.aclose()
    assert "private exporter exception" not in caplog.text


async def test_callbacks_reject_untrusted_payloads_and_error_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock(spec=Client)
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    runtime = AiTracing(enabled_settings())
    trace = runtime.start("chat", AiTraceContext(uuid4(), 1))
    assert trace is not None
    run_id = uuid4()
    await trace.on_tool_start({"name": "private-tool"}, "private input", run_id=run_id)
    await trace.on_tool_start(
        {"name": "read_applicant", "private": "identity"},
        "private input",
        run_id=run_id,
        metadata={"private": "identity"},
    )
    await trace.on_tool_error(RuntimeError("private traceback"), run_id=run_id)
    trace.finish("failed")
    await runtime.aclose()
    assert client.create_run.call_count == 2
    raw = repr(client.mock_calls)
    assert "private" not in raw
    assert "execution_failed" in raw


async def test_model_close_error_still_joins_tracing_close() -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def close_trace() -> None:
        entered.set()
        await release.wait()

    runtime = object.__new__(OpenAiAgentDriver)
    runtime.model = Mock()
    runtime.model.root_async_client.close = AsyncMock(side_effect=ValueError("failed"))
    runtime.tracing = cast(AiTracing, SimpleNamespace(aclose=close_trace))
    closing = asyncio.create_task(runtime.aclose())
    await entered.wait()
    await asyncio.sleep(0)
    assert not closing.done()
    release.set()
    with pytest.raises(ValueError, match="failed"):
        await closing


async def test_driver_close_cancellation_joins_both_owned_coroutines() -> None:
    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def close() -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    runtime = object.__new__(OpenAiAgentDriver)
    runtime.model = Mock()
    runtime.model.root_async_client.close = AsyncMock()
    runtime.tracing = cast(AiTracing, SimpleNamespace(aclose=close))
    closing = asyncio.create_task(runtime.aclose())
    await entered.wait()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert cleaned.is_set()


@pytest.mark.parametrize("status", ["blocked", "failed", "canceled"])
async def test_trace_finishes_with_safe_status_when_stream_stops(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    client = Mock(spec=Client)
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    if status == "blocked":
        script = Script(rounds=[[AIMessageChunk(content='{"reason":"out_of_scope"}')]])
    elif status == "failed":
        script = Script(rounds=[[AIMessageChunk(content="private malformed answer")]])
    else:
        script = Script(
            rounds=[[prepare()], [AIMessageChunk(content="first")]],
            release=asyncio.Event(),
        )
    runtime = driver(monkeypatch, script, enabled_settings())
    stream = runtime.stream(
        sources("chat" if status == "blocked" else "applicant_recommendation"),
        "private request",
        [],
        AsyncMock(return_value=[]),
        gate=AsyncMock(),
    )
    try:
        if status == "failed":
            with pytest.raises(ValueError):
                _ = [chunk async for chunk in stream]
        elif status == "blocked":
            assert len([chunk async for chunk in stream]) == 1
        else:
            # 첫 최종 토큰 뒤 모델이 기다려도 소비자는 즉시 받고 닫을 수 있다.
            assert await asyncio.wait_for(anext(stream), 1) == "first"
            assert not script.canceled.is_set()
            await asyncio.wait_for(stream.aclose(), 1)
            assert script.canceled.is_set()
        await runtime.tracing.aclose()
        root_end = client.update_run.call_args.kwargs
        assert root_end["extra"]["metadata"]["status"] == status
        assert root_end["error"] == (
            None if status == "blocked" else f"execution_{status}"
        )
        assert "private" not in repr(client.mock_calls)
    finally:
        await stream.aclose()
        await runtime.tracing.aclose()


async def test_exporter_initialization_failure_does_not_disable_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tracing, "Client", Mock(side_effect=ValueError("private secret"))
    )
    runtime = driver(
        monkeypatch,
        Script(rounds=[[prepare()], [AIMessageChunk(content="answer")]]),
        enabled_settings(),
    )
    assert runtime.tracing.client is None
    assert [
        chunk
        async for chunk in runtime.stream(
            sources(), "request", [], AsyncMock(return_value=[]), gate=AsyncMock()
        )
    ] == ["answer"]


async def test_worker_initialization_failure_closes_client_and_disables_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock(spec=Client)
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    monkeypatch.setattr(
        threading.Thread, "start", Mock(side_effect=RuntimeError("no thread"))
    )
    runtime = AiTracing(enabled_settings())
    assert runtime.client is None and runtime.worker is None
    assert runtime.start("chat", None) is None
    client.close.assert_called_once_with(timeout=0)
    await runtime.aclose()


async def test_real_sdk_rate_limit_is_not_retried_or_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests_seen: list[str] = []
    sleeps = Mock()
    monkeypatch.setattr("langsmith.client.time.sleep", sleeps)

    def limited(
        self: requests.Session, method: str, url: str, **kwargs: Any
    ) -> requests.Response:
        assert kwargs["timeout"] == (1, 1)
        requests_seen.append(method)
        response = requests.Response()
        response.status_code = 429
        response.url = url
        response.headers["Retry-After"] = "3600"
        response._content = b'{"error":"private exporter response"}'
        return response

    monkeypatch.setattr(requests.Session, "request", limited)
    runtime = AiTracing(enabled_settings())
    trace = runtime.start("chat", None)
    assert trace is not None
    trace.finish("completed")
    await asyncio.wait_for(runtime.aclose(), 1)
    assert requests_seen == ["POST", "PATCH"]
    sleeps.assert_not_called()


async def test_bounded_queue_drops_immediately_and_preserves_fifo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()
    client = Mock(spec=Client)

    def export(**payload: Any) -> None:
        if payload["name"] == "ai_turn":
            entered.set()
            release.wait(timeout=2)

    client.create_run.side_effect = export
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    runtime = AiTracing(enabled_settings())
    runtime.start("chat", None)
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        # 전송 worker가 막혀도 요청 thread는 기다리지 않고 유한 큐에 추가한다.
        for index in range(TRACE_QUEUE_SIZE + 5):
            runtime.create_run(name=str(index))
        assert runtime.queue.qsize() == TRACE_QUEUE_SIZE
    finally:
        release.set()
        await runtime.aclose()
    assert [call.kwargs["name"] for call in client.create_run.call_args_list] == [
        "ai_turn",
        *map(str, range(TRACE_QUEUE_SIZE)),
    ]


async def test_exporter_shutdown_waits_off_loop_with_finite_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()
    timeouts: list[float] = []

    def export(**payload: Any) -> None:
        entered.set()
        release.wait(timeout=2)

    def close(*, timeout: float) -> None:
        timeouts.append(timeout)

    client = Mock(spec=Client)
    client.create_run.side_effect = export
    client.close.side_effect = close
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    settings = enabled_settings().model_copy(update={"shutdown_timeout_seconds": 0.1})
    runtime = AiTracing(settings)
    runtime.start("chat", None)
    task = asyncio.create_task(runtime.aclose())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        await asyncio.wait_for(task, 1)
        assert timeouts == []
        assert runtime.worker is not None and runtime.worker.daemon
        assert runtime.worker.is_alive()
    finally:
        release.set()
        await task
        assert runtime.worker is not None
        await asyncio.to_thread(runtime.worker.join, 1)
    assert timeouts == [0]
