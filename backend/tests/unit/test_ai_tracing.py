"""LangSmith 추적의 명시적 설정·비밀 보호·비차단 수명을 검증한다."""

import asyncio
import json
import threading
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_openai import ChatOpenAI
from langsmith import Client, get_tracing_context, tracing_context
from pydantic import SecretStr, ValidationError

from app.agents import factory, tracing
from app.agents.factory import OpenAiAgentDriver
from app.agents.tools import SourceTools
from app.agents.tracing import AiTraceContext, AiTracing
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


@pytest.fixture
def native_exports(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []

    def capture(self: Client, body: bytes, **kwargs: Any) -> None:
        batches.append(json.loads(body))

    monkeypatch.setattr(Client, "_post_batch_ingest_runs", capture)

    def client(**kwargs: Any) -> Client:
        return Client(
            **kwargs,
            info={
                "batch_ingest_config": {
                    "use_multipart_endpoint": False,
                    "size_limit": 100,
                    "scale_up_nthreads_limit": 1,
                    "scale_up_qsize_trigger": 1000,
                }
            },
        )

    monkeypatch.setattr(tracing, "Client", client)
    return batches


async def test_native_graph_records_full_io_and_nested_guard_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
    native_exports: list[dict[str, Any]],
) -> None:
    script = Script(
        rounds=[
            [AIMessageChunk(content='{"reason":"allowed"}')],
            [prepare()],
            [
                AIMessageChunk(
                    content="native answer",
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
    request_id = uuid4()
    try:
        result = [
            chunk
            async for chunk in runtime.stream(
                sources("chat"),
                "original request",
                ["original history"],
                AsyncMock(return_value=[{"facts": "authorized resource"}]),
                gate=AsyncMock(),
                trace_context=AiTraceContext(request_id, 2),
            )
        ]
        assert result == ["native answer"]
    finally:
        await runtime.tracing.aclose()
    posts = [run for batch in native_exports for run in batch.get("post", [])]
    roots = [run for run in posts if not run.get("parent_run_id")]
    assert len(roots) == 1
    root = roots[0]
    assert root["name"] == "ai_turn"
    assert all(run["trace_id"] == root["id"] for run in posts)
    by_id = {run["id"]: run for run in posts}
    guard = next(run for run in posts if run["name"] == "input_guard")
    assert "InputGuardMiddleware" in by_id[guard["parent_run_id"]]["name"]
    assert guard["parent_run_id"] != root["id"]
    assert any(
        run["run_type"] == "tool" and run["name"] == "prepare_recommendations"
        for run in posts
    )
    raw = json.dumps(native_exports, ensure_ascii=False)
    for value in (
        "original request",
        "original history",
        "authorized resource",
        "native answer",
        "input_tokens",
    ):
        assert value in raw
    assert str(request_id) not in raw
    assert root["extra"]["metadata"]["request_attempt"] == 2


@pytest.mark.parametrize("hidden", [False, True])
async def test_native_hiding_and_configured_secret_masking(
    monkeypatch: pytest.MonkeyPatch,
    native_exports: list[dict[str, Any]],
    hidden: bool,
) -> None:
    settings = enabled_settings().model_copy(
        update={
            "langsmith_hide_inputs": hidden,
            "langsmith_hide_outputs": hidden,
            "openai_api_key": SecretStr("configured-openai-credential"),
        }
    )
    runtime = driver(
        monkeypatch,
        Script(rounds=[[prepare()], [AIMessageChunk(content="answer")]]),
        settings,
    )
    try:
        _ = [
            chunk
            async for chunk in runtime.stream(
                sources(),
                "configured-openai-credential original input",
                [],
                AsyncMock(return_value=[]),
                gate=AsyncMock(),
            )
        ]
    finally:
        await runtime.tracing.aclose()
    raw = json.dumps(native_exports)
    assert "configured-openai-credential" not in raw
    assert "synthetic-tracing-key" not in raw
    runs = [
        run
        for batch in native_exports
        for key in ("post", "patch")
        for run in batch.get(key, [])
    ]
    if hidden:
        assert all(not run.get("inputs") and not run.get("outputs") for run in runs)
    else:
        assert "original input" in raw and "[REDACTED]" in raw
        assert any(run.get("outputs") for run in runs)


async def test_native_context_excludes_ambient_parent_metadata_tags_and_replicas(
    monkeypatch: pytest.MonkeyPatch,
    native_exports: list[dict[str, Any]],
) -> None:
    from langsmith.run_trees import RunTree

    runtime = driver(
        monkeypatch,
        Script(rounds=[[prepare()], [AIMessageChunk(content="answer")]]),
        enabled_settings(),
    )
    parent = RunTree(name="unrelated-parent", inputs={}, client=runtime.tracing.client)
    stream = runtime.stream(
        sources(), "request", [], AsyncMock(return_value=[]), gate=AsyncMock()
    )
    try:
        with tracing_context(
            enabled=True,
            parent=parent,
            metadata={"unrelated": "ambient identity"},
            tags=["ambient tag"],
            replicas=[{"project_name": "unexpected-replica"}],
        ):
            assert await asyncio.create_task(anext(stream)) == "answer"
            assert get_tracing_context()["parent"] is parent
            with pytest.raises(StopAsyncIteration):
                await asyncio.create_task(anext(stream))
    finally:
        await stream.aclose()
        await runtime.tracing.aclose()
    raw = json.dumps(native_exports)
    for forbidden in (
        str(parent.id),
        "unrelated-parent",
        "ambient identity",
        "ambient tag",
        "unexpected-replica",
    ):
        assert forbidden not in raw


async def test_first_token_and_cancel_do_not_wait_for_native_export(
    monkeypatch: pytest.MonkeyPatch,
    native_exports: list[dict[str, Any]],
) -> None:
    script = Script(
        rounds=[[prepare()], [AIMessageChunk(content="first")]], release=asyncio.Event()
    )
    runtime = driver(monkeypatch, script, enabled_settings())
    stream = runtime.stream(
        sources(), "request", [], AsyncMock(return_value=[]), gate=AsyncMock()
    )
    try:
        assert await asyncio.wait_for(anext(stream), 2) == "first"
        assert not script.canceled.is_set()
        await asyncio.wait_for(stream.aclose(), 2)
        assert script.canceled.is_set()
    finally:
        await stream.aclose()
        await runtime.tracing.aclose()
    assert native_exports


async def test_sdk_failure_keeps_model_stream_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock(spec=Client)
    client.create_run.side_effect = RuntimeError("export unavailable")
    client.update_run.side_effect = RuntimeError("export unavailable")
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    runtime = driver(
        monkeypatch,
        Script(rounds=[[prepare()], [AIMessageChunk(content="answer")]]),
        enabled_settings(),
    )
    try:
        assert [
            chunk
            async for chunk in runtime.stream(
                sources(), "request", [], AsyncMock(return_value=[]), gate=AsyncMock()
            )
        ] == ["answer"]
    finally:
        await runtime.tracing.aclose()


async def test_native_errors_keep_diagnostics_and_mask_configured_credentials(
    monkeypatch: pytest.MonkeyPatch,
    native_exports: list[dict[str, Any]],
) -> None:
    key = "configured-openai-credential"
    settings = enabled_settings().model_copy(update={"openai_api_key": SecretStr(key)})
    runtime = driver(monkeypatch, Script(rounds=[[prepare()]]), settings)
    try:
        with pytest.raises(RuntimeError, match="validation failed"):
            _ = [
                chunk
                async for chunk in runtime.stream(
                    sources(),
                    "request",
                    [],
                    AsyncMock(return_value=[]),
                    gate=AsyncMock(
                        side_effect=RuntimeError(f"{key}: validation failed")
                    ),
                )
            ]
    finally:
        await runtime.tracing.aclose()
    raw = json.dumps(native_exports)
    assert key not in raw
    assert "validation failed" in raw
    assert "[REDACTED]" in raw


def test_native_model_serialization_keeps_api_key_as_secret_reference() -> None:
    key = "configured-openai-credential"
    model = ChatOpenAI(model="gpt-6-luna", api_key=SecretStr(key))
    serialized = json.dumps(model.to_json(), default=str)
    assert key not in serialized
    assert "OPENAI_API_KEY" in serialized


async def test_native_shutdown_is_finite_off_loop_and_model_failure_joins_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()
    client = Mock(spec=Client)

    def close(*, timeout: float) -> None:
        assert timeout == 0.1
        entered.set()
        release.wait(timeout=1)

    client.close.side_effect = close
    monkeypatch.setattr(tracing, "Client", Mock(return_value=client))
    settings = enabled_settings().model_copy(update={"shutdown_timeout_seconds": 0.1})
    runtime = object.__new__(OpenAiAgentDriver)
    runtime.tracing = AiTracing(settings)
    runtime.model = Mock()
    runtime.model.root_async_client.close = AsyncMock(
        side_effect=ValueError("model close failed")
    )
    closing = asyncio.create_task(runtime.aclose())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        assert not closing.done()
        with pytest.raises(ValueError, match="model close failed"):
            await asyncio.wait_for(closing, 1)
    finally:
        release.set()


def test_native_client_supported_daemon_and_uncompressed_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langsmith import utils

    monkeypatch.setenv("LANGSMITH_USE_DAEMON", "false")
    monkeypatch.setenv("LANGSMITH_DISABLE_RUN_COMPRESSION", "false")
    cast(Any, utils.get_env_var).cache_clear()
    assert utils.get_env_var("USE_DAEMON") == "false"
    client = Mock(return_value=Mock(spec=Client))
    monkeypatch.setattr(tracing, "Client", client)
    runtime = AiTracing(enabled_settings())
    assert utils.get_env_var("USE_DAEMON") == "true"
    assert utils.get_env_var("DISABLE_RUN_COMPRESSION") == "true"
    assert client.call_args.kwargs["auto_batch_tracing"] is True
    runtime.client = None
