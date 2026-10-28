"""실제 create_agent 그래프에서 검증 게이트와 최종 토큰 전달 경계를 검사한다."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain.agents import create_agent
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from app.agents import factory
from app.agents.factory import OpenAiAgentDriver
from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.types import RecommendationPlan
from app.core.config import Settings
from app.services.ai_sources import SourceReader


@dataclass
class Script:
    rounds: list[list[AIMessageChunk]]
    calls: list[dict[str, Any]] = field(default_factory=list)
    release: asyncio.Event | None = None
    canceled: asyncio.Event = field(default_factory=asyncio.Event)


class ScriptedModel(BaseChatModel):
    """외부 연결 없이 도구 호출과 실제 비동기 텍스트 청크를 재생한다."""

    script: Script

    @property
    def _llm_type(self) -> str:
        return "scripted-react-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        return self.bind(tools=list(tools), tool_choice=tool_choice, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("Tests must use genuine streaming")

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        index = len(self.script.calls)
        self.script.calls.append({"messages": messages, **kwargs})
        try:
            for chunk in self.script.rounds[index]:
                yield ChatGenerationChunk(message=chunk)
                if index == 1 and self.script.release is not None and chunk.text:
                    await self.script.release.wait()
        finally:
            if index == 1:
                self.script.canceled.set()


def prepare(
    *, name: str = "prepare_recommendations", args: str | None = None
) -> AIMessageChunk:
    plan = RecommendationPlan(intent="clarify", selections=[], guidance="조건 확인")
    return AIMessageChunk(
        content="숨길 중간 발화",
        tool_call_chunks=[
            {
                "name": name,
                "args": args
                if args is not None
                else json.dumps({"plan": plan.model_dump()}),
                "id": "call_prepare",
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )


def runtime(
    monkeypatch: pytest.MonkeyPatch,
    script: Script,
    *,
    purpose: str = "applicant_recommendation",
) -> tuple[OpenAiAgentDriver, SourceTools]:
    model = ScriptedModel(script=script)
    monkeypatch.setattr(factory, "ChatOpenAI", lambda **kwargs: model)
    driver = OpenAiAgentDriver(Settings(_env_file=None))
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose=purpose)
    sources = SourceTools(reader, max_sources=30, max_calls=8)
    monkeypatch.setattr(sources, "build", lambda: [])
    return driver, sources


async def test_single_graph_gate_then_immediate_final_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = asyncio.Event()
    script = Script(
        rounds=[
            [prepare()],
            [
                AIMessageChunk(content=[{"type": "reasoning", "reasoning": "비공개"}]),
                AIMessageChunk(content="첫 토큰"),
                AIMessageChunk(content=" 다음"),
            ],
        ],
        release=release,
    )
    driver, sources = runtime(monkeypatch, script)
    create = Mock(wraps=create_agent)
    monkeypatch.setattr(factory, "create_agent", create)
    gate = AsyncMock()
    previous = AsyncMock(return_value=[{"key": "이전 결과"}])
    stream = driver.stream(sources, "요청", ["이전 질문"], previous, gate=gate)
    # 모델이 첫 최종 텍스트 뒤 대기해도 그 토큰을 즉시 전달한다.
    assert await asyncio.wait_for(anext(stream), 2) == "첫 토큰"
    assert not script.canceled.is_set()
    release.set()
    assert [value async for value in stream] == [" 다음"]
    assert create.call_count == 1
    gate.assert_awaited_once()
    previous.assert_awaited_once()
    assert script.calls[0]["tool_choice"] == "required"
    assert script.calls[0]["parallel_tool_calls"] is False
    assert "tools" not in script.calls[1]
    assert "서버 검증이 끝났다" in script.calls[1]["messages"][0].content
    assert "이전 결과" in script.calls[0]["messages"][1].content
    assert sources.calls == 1


async def test_gate_failure_prevents_any_final_model_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Script(rounds=[[prepare()], [AIMessageChunk(content="누출")]])
    driver, sources = runtime(monkeypatch, script)
    gate = AsyncMock(side_effect=ValueError("unverified IDs"))
    with pytest.raises(ValueError):
        _ = [
            value
            async for value in driver.stream(
                sources, "요청", [], AsyncMock(return_value=[]), gate=gate
            )
        ]
    assert len(script.calls) == 1


@pytest.mark.parametrize(
    "chunks",
    [
        [AIMessageChunk(content="검증 생략")],
        [prepare(args='{"plan": {"intent": "invalid"}}')],
        [prepare(name="unknown_tool")],
        [
            prepare(),
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": "prepare_recommendations",
                        "args": "{}",
                        "id": "second",
                        "index": 1,
                    }
                ],
            ),
        ],
    ],
)
async def test_missing_gate_malformed_or_parallel_tools_fail_closed(
    monkeypatch: pytest.MonkeyPatch, chunks: list[AIMessageChunk]
) -> None:
    script = Script(rounds=[chunks])
    driver, sources = runtime(monkeypatch, script)
    gate = AsyncMock()
    with pytest.raises(ValueError):
        _ = [
            value
            async for value in driver.stream(
                sources, "요청", [], AsyncMock(return_value=[]), gate=gate
            )
        ]
    gate.assert_not_awaited()
    assert len(script.calls) == 1


async def test_empty_final_answer_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    script = Script(rounds=[[prepare()], [AIMessageChunk(content="")]])
    driver, sources = runtime(monkeypatch, script)
    with pytest.raises(ValueError, match="Missing validated final answer"):
        _ = [
            value
            async for value in driver.stream(
                sources, "요청", [], AsyncMock(return_value=[]), gate=AsyncMock()
            )
        ]


async def test_close_cancels_model_without_waiting_for_full_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Script(
        rounds=[[prepare()], [AIMessageChunk(content="첫 토큰")]],
        release=asyncio.Event(),
    )
    driver, sources = runtime(monkeypatch, script)
    stream = driver.stream(
        sources, "요청", [], AsyncMock(return_value=[]), gate=AsyncMock()
    )
    assert await asyncio.wait_for(anext(stream), 2) == "첫 토큰"
    assert not script.canceled.is_set()
    await asyncio.wait_for(stream.aclose(), 2)
    assert script.canceled.is_set()


async def test_input_budget_covers_final_frozen_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Script(rounds=[[prepare()], [AIMessageChunk(content="누출")]])
    driver, sources = runtime(monkeypatch, script)

    async def gate(plan: RecommendationPlan) -> None:
        plan.guidance = "큰 검증된 근거 " * 10000

    with pytest.raises(ToolBudgetExceeded):
        _ = [
            value
            async for value in driver.stream(
                sources, "요청", [], AsyncMock(return_value=[]), gate=gate
            )
        ]
    assert len(script.calls) == 1


async def test_blocked_input_never_loads_previous_or_calls_react_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.guards import InputBlocked

    script = Script(rounds=[])
    driver, sources = runtime(monkeypatch, script, purpose="chat")
    guard = Mock()
    guard.check = AsyncMock(side_effect=InputBlocked("고정 안내"))
    monkeypatch.setattr(factory, "InputGuard", lambda model: guard)
    previous = AsyncMock(return_value=[{"private": str(uuid4())}])
    gate = AsyncMock()
    result = [
        value
        async for value in driver.stream(sources, "거절 요청", [], previous, gate=gate)
    ]
    assert result == ["고정 안내"]
    previous.assert_not_awaited()
    assert script.calls == []
    gate.assert_awaited_once()
    assert gate.await_args is not None
    assert gate.await_args.args[0].intent == "clarify"


async def test_allowed_guard_precedes_context_loader_and_uses_one_react_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.guards import GuardDecision

    script = Script(
        rounds=[[prepare()], [AIMessageChunk(content="조건을 알려 주세요.")]]
    )
    driver, sources = runtime(monkeypatch, script, purpose="chat")
    guard = Mock()
    guard.check = AsyncMock(return_value=GuardDecision(reason="allowed"))
    monkeypatch.setattr(factory, "InputGuard", lambda model: guard)

    async def previous() -> list[dict[str, object]]:
        guard.check.assert_awaited_once_with("새 요청", ["이전 요청"])
        assert script.calls == []
        return [{"title": "현재 권한으로 확인한 이전 자료"}]

    result = [
        value
        async for value in driver.stream(
            sources, "새 요청", ["이전 요청"], previous, gate=AsyncMock()
        )
    ]
    assert result == ["조건을 알려 주세요."]
    assert len(script.calls) == 2


async def test_guard_unavailable_does_not_load_context_or_allow_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.guards import GuardUnavailable

    script = Script(rounds=[])
    driver, sources = runtime(monkeypatch, script, purpose="chat")
    guard = Mock()
    guard.check = AsyncMock(side_effect=GuardUnavailable())
    monkeypatch.setattr(factory, "InputGuard", lambda model: guard)
    previous, gate = AsyncMock(), AsyncMock()
    with pytest.raises(GuardUnavailable):
        _ = [
            value
            async for value in driver.stream(sources, "요청", [], previous, gate=gate)
        ]
    previous.assert_not_awaited()
    gate.assert_not_awaited()
    assert script.calls == []


async def test_final_phase_freezes_only_gate_approved_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.types import Reference, Resource, Selection

    selected = Resource(
        reference=Reference(kind="person", resource_id=uuid4(), fingerprint="a" * 64),
        title="선택한 사람",
        is_demo=False,
        facts={"role": "디자이너"},
    )
    unselected = selected.model_copy(
        update={
            "reference": Reference(
                kind="person", resource_id=uuid4(), fingerprint="b" * 64
            ),
            "title": "선택하지 않은 사람",
        }
    )
    plan = RecommendationPlan(
        intent="recommend",
        selections=[Selection(key=selected.reference.key, reason="역할", evidence=[])],
        guidance="확인",
    )
    script = Script(
        rounds=[
            [prepare(args=json.dumps({"plan": plan.model_dump()}))],
            [AIMessageChunk(content="등록된 역할을 확인하세요.")],
        ]
    )
    driver, sources = runtime(monkeypatch, script)
    sources.observed = {value.reference.key: value for value in (selected, unselected)}
    gate = AsyncMock()
    _ = [
        value
        async for value in driver.stream(
            sources, "요청", [], AsyncMock(return_value=[]), gate=gate
        )
    ]
    final_system = script.calls[1]["messages"][0].content
    assert selected.reference.key in final_system
    assert selected.title in final_system
    assert unselected.reference.key not in final_system
    assert unselected.title not in final_system
    assert "tools" not in script.calls[1]
    gate.assert_awaited_once()


@pytest.mark.parametrize("reason", ["max_output_tokens", "content_filter"])
async def test_provider_incomplete_response_cannot_finish_successfully(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    script = Script(
        rounds=[
            [prepare()],
            [
                AIMessageChunk(content="완성되지 않은 문장"),
                AIMessageChunk(
                    content="",
                    response_metadata={
                        "status": "incomplete",
                        "incomplete_details": {"reason": reason},
                    },
                ),
            ],
        ]
    )
    driver, sources = runtime(monkeypatch, script)
    response = driver.stream(
        sources, "요청", [], AsyncMock(return_value=[]), gate=AsyncMock()
    )
    assert await anext(response) == "완성되지 않은 문장"
    expected = ToolBudgetExceeded if reason == "max_output_tokens" else ValueError
    with pytest.raises(expected):
        await anext(response)
