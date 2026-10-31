"""단일 ReAct 실행의 검증된 최종 모델 텍스트만 실시간으로 전달한다."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol, cast

import tiktoken
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    AgentState,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    messages_to_dict,
)
from langchain_core.runnables.schema import StreamEvent
from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agents.guards import InputBlocked, InputGuard, InputGuardMiddleware
from app.agents.prompts import AGENT_PROMPT, FINAL_ANSWER_PROMPT
from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.tracing import (
    FINAL_ANSWER_TAG,
    AiTraceContext,
    AiTracing,
)
from app.agents.types import PreviousContext, RecommendationGate, RecommendationPlan
from app.core.config import Settings

Gate = RecommendationGate

REQUEST_MESSAGE_ID = "request"


class AgentDriver(Protocol):
    def stream(
        self,
        sources: SourceTools,
        content: str,
        history: list[str],
        previous: PreviousContext,
        *,
        gate: RecommendationGate,
        trace_context: AiTraceContext | None = None,
    ) -> AsyncIterator[str]: ...


class RequestContext(AgentMiddleware[AgentState[None], None]):
    """입력 검사가 허용한 뒤에만 이전 자료를 현재 권한으로 다시 읽는다."""

    def __init__(
        self,
        sources: SourceTools,
        content: str,
        history: list[str],
        previous: PreviousContext,
    ) -> None:
        self.sources, self.content = sources, content
        self.history, self.previous = history, previous

    async def abefore_agent(
        self, state: AgentState[None], runtime: Runtime[None]
    ) -> dict[str, object]:
        payload = {
            "purpose": self.sources.reader.context.purpose,
            "currentTime": datetime.now(UTC).isoformat(),
            "previousUserMessages": self.history,
            "previousResults": await self.previous(),
            "request": self.content,
        }
        return {
            "messages": [
                HumanMessage(
                    id=REQUEST_MESSAGE_ID,
                    content=json.dumps(payload, ensure_ascii=False),
                )
            ]
        }


class InputBudget(AgentMiddleware[AgentState[None], None]):
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.encoder = tiktoken.get_encoding("o200k_base")
        self.calls = 0

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler: Callable[[ModelRequest[None]], Awaitable[ModelResponse[None]]],
    ) -> ModelResponse[None]:
        self.calls += 1
        if self.calls > 6:
            raise ToolBudgetExceeded()
        messages = list(request.messages)
        if request.system_message is not None:
            messages.insert(0, request.system_message)
        serialized = json.dumps(
            {
                "messages": messages_to_dict(messages),
                "tools": [convert_to_openai_tool(value) for value in request.tools],
            },
            ensure_ascii=False,
        )
        # 특수 토큰처럼 보이는 사용자 문자열도 일반 입력으로 센다.
        if len(self.encoder.encode(serialized, disallowed_special=())) > self.maximum:
            raise ToolBudgetExceeded()
        return await handler(request)


class RecommendationPhase(AgentMiddleware[AgentState[None], None]):
    """서버 게이트 성공 뒤 조회 도구를 제거하고 최종 모델 호출을 식별한다."""

    def __init__(self, sources: SourceTools, gate: RecommendationGate) -> None:
        self.sources, self.gate = sources, gate
        self.plan: RecommendationPlan | None = None
        self.frozen = ""

    async def prepare(self, plan: RecommendationPlan) -> str:
        if self.plan is not None:
            raise ValueError("Recommendation already prepared")
        self.sources.count_call()
        await self.gate(plan)
        # 서버 검증 이후에만 후보와 근거를 고정한다. 이후 도구는 제공하지 않는다.
        self.frozen = json.dumps(
            {
                "plan": plan.model_dump(mode="json"),
                "resources": [
                    self.sources.observed[item.key].model_input()
                    for item in plan.selections
                ],
            },
            ensure_ascii=False,
        )
        self.plan = plan.model_copy(deep=True)
        return "서버 검증을 통과했습니다. 확정된 자료만 사용해 최종 답변을 작성하세요."

    async def awrap_model_call(
        self,
        request: ModelRequest[None],
        handler: Callable[[ModelRequest[None]], Awaitable[ModelResponse[None]]],
    ) -> ModelResponse[None]:
        if self.plan is None:
            return await handler(
                request.override(
                    tool_choice="required",
                    model_settings={"parallel_tool_calls": False},
                )
            )
        return await handler(
            request.override(
                model=request.model.model_copy(update={"tags": [FINAL_ANSWER_TAG]}),
                tools=[],
                tool_choice=None,
                model_settings={},
                system_message=SystemMessage(
                    content=(
                        f"{AGENT_PROMPT}\n{FINAL_ANSWER_PROMPT}\n"
                        f"## 확정 자료 (JSON 데이터)\n```json\n{self.frozen}\n```"
                    )
                ),
            )
        )

    async def aafter_model(
        self, state: AgentState[None], runtime: Runtime[None]
    ) -> None:
        message = state["messages"][-1]
        if not isinstance(message, AIMessage) or message.invalid_tool_calls:
            raise ValueError("Invalid agent response")
        status = message.response_metadata.get("status")
        if status is not None and status != "completed":
            details = message.response_metadata.get("incomplete_details")
            if (
                isinstance(details, dict)
                and details.get("reason") == "max_output_tokens"
            ):
                raise ToolBudgetExceeded()
            # 제공자가 잘린 응답을 반환해도 완성 답변으로 저장하지 않는다.
            raise ValueError("Incomplete provider response")
        if self.plan is None:
            # 도구 병렬 호출을 제공자가 무시해도 게이트와 조회가 경쟁하지 못한다.
            if len(message.tool_calls) != 1:
                raise ValueError("Agent must call one tool before answering")
        elif message.tool_calls:
            raise ValueError("Final answer cannot call tools")

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    ) -> ToolMessage | Command[object]:
        result = await handler(request)
        if isinstance(result, ToolMessage) and result.status == "error":
            raise ValueError("Invalid agent tool call")
        return result


class OpenAiAgentDriver:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = ChatOpenAI(
            model=settings.ai_model,
            api_key=settings.openai_api_key,
            use_responses_api=True,
            store=False,
            use_previous_response_id=False,
            reasoning={"effort": settings.ai_reasoning_effort},
            max_completion_tokens=settings.ai_max_output_tokens,
            timeout=min(settings.ai_timeout_seconds, 45),
            max_retries=0,
        )
        self.tracing = AiTracing(settings)

    async def aclose(self) -> None:
        results = await asyncio.gather(
            self.model.root_async_client.close(),
            self.tracing.aclose(),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result

    async def stream(
        self,
        sources: SourceTools,
        content: str,
        history: list[str],
        previous: PreviousContext,
        *,
        gate: RecommendationGate,
        trace_context: AiTraceContext | None = None,
    ) -> AsyncGenerator[str]:
        phase = RecommendationPhase(sources, gate)

        @tool
        async def prepare_recommendations(plan: RecommendationPlan) -> str:
            """실제 조회 후보·이유를 서버에 검증받고 최종 답변 단계를 시작한다."""
            return await phase.prepare(plan)

        middleware: list[AgentMiddleware[AgentState[None], None]] = []
        if sources.reader.context.purpose == "chat":
            middleware.append(
                InputGuardMiddleware(InputGuard(self.model), content, history)
            )
        middleware.extend(
            [
                RequestContext(sources, content, history, previous),
                phase,
                InputBudget(self.settings.ai_max_input_tokens),
            ]
        )
        agent = create_agent(
            model=self.model,
            tools=[*sources.build(), prepare_recommendations],
            system_prompt=AGENT_PROMPT,
            middleware=middleware,
        )
        emitted = False
        events = cast(
            AsyncGenerator[StreamEvent],
            agent.astream_events(
                {"messages": [HumanMessage(id=REQUEST_MESSAGE_ID, content=content)]},
                config={
                    "recursion_limit": 32,
                    **self.tracing.config(
                        sources.reader.context.purpose, trace_context
                    ),
                },
                version="v2",
            ),
        )
        try:
            try:
                while True:
                    # anext마다 새 task에서 실행될 수 있으므로 yield를 가로질러
                    # contextvars를 유지하지 않고 각 대기·정리에 추적 설정을 적용한다.
                    with self.tracing.context():
                        try:
                            event = await anext(events)
                        except StopAsyncIteration:
                            break
                    is_final = FINAL_ANSWER_TAG in event.get("tags", [])
                    if event["event"] != "on_chat_model_stream" or not is_final:
                        continue
                    chunk = event["data"].get("chunk")
                    if isinstance(chunk, AIMessageChunk) and chunk.text:
                        if phase.plan is None:
                            raise ValueError("Answer before server validation")
                        emitted = True
                        # text는 추론·도구 인자가 아닌 텍스트 블록만 추출한다.
                        yield str(chunk.text)
            finally:
                with self.tracing.context():
                    await events.aclose()
        except InputBlocked as error:
            await gate(
                RecommendationPlan(
                    intent="clarify", selections=[], guidance=error.guidance
                )
            )
            yield error.guidance
            return
        if phase.plan is None or not emitted:
            raise ValueError("Missing validated final answer")
