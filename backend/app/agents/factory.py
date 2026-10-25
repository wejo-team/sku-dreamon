"""조회 에이전트와 도구 없는 답변 작성기를 Luna Responses API로 실행한다."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Protocol

import tiktoken
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    messages_to_dict,
)
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from langsmith import tracing_context

from app.agents.prompts import PLANNER_PROMPT, WRITER_PROMPT
from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.types import RecommendationPlan, Resource
from app.core.config import Settings


class AgentDriver(Protocol):
    async def plan(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: list[dict[str, object]],
    ) -> RecommendationPlan: ...

    def write(
        self, plan: RecommendationPlan, resources: list[Resource], content: str
    ) -> AsyncIterator[str]: ...


class InputBudget(AgentMiddleware[AgentState[RecommendationPlan], None]):
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.encoder = tiktoken.get_encoding("o200k_base")

    async def abefore_model(
        self, state: AgentState[RecommendationPlan], runtime: Runtime[None]
    ) -> dict[str, object] | None:
        if sum(isinstance(item, AIMessage) for item in state["messages"]) >= 6:
            raise ToolBudgetExceeded()
        serialized = json.dumps(messages_to_dict(state["messages"]), ensure_ascii=False)
        # 토크나이저의 특수 토큰처럼 보이는 사용자 입력도 일반 문자열로 센다.
        if len(self.encoder.encode(serialized, disallowed_special=())) > self.maximum:
            raise ToolBudgetExceeded()
        return None


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

    async def plan(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: list[dict[str, object]],
    ) -> RecommendationPlan:
        agent = create_agent(
            model=self.model,
            tools=tools.build(),
            system_prompt=PLANNER_PROMPT,
            response_format=ProviderStrategy(RecommendationPlan, strict=True),
            middleware=[
                InputBudget(self.settings.ai_max_input_tokens),
            ],
        )
        payload = {
            "purpose": tools.reader.context.purpose,
            "currentTime": datetime.now(UTC).isoformat(),
            "previousUserMessages": history,
            "previousResults": previous,
            "request": content,
        }
        with tracing_context(enabled=False):
            state = await agent.ainvoke(
                {
                    "messages": [
                        HumanMessage(content=json.dumps(payload, ensure_ascii=False))
                    ]
                },
                config={"recursion_limit": 24, "callbacks": []},
            )
        plan = state.get("structured_response")
        if not isinstance(plan, RecommendationPlan):
            raise ValueError("Missing structured recommendation")
        return plan

    async def write(
        self, plan: RecommendationPlan, resources: list[Resource], content: str
    ) -> AsyncIterator[str]:
        queue: asyncio.Queue[str | Exception | None] = asyncio.Queue(maxsize=1)

        async def produce() -> None:
            try:
                async for part in self._write(plan, resources, content):
                    await queue.put(part)
            except Exception as error:
                await queue.put(error)
            else:
                await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _write(
        self, plan: RecommendationPlan, resources: list[Resource], content: str
    ) -> AsyncIterator[str]:
        payload = json.dumps(
            {
                "request": content,
                "plan": plan.model_dump(),
                "resources": [resource.model_input() for resource in resources],
            },
            ensure_ascii=False,
        )
        budget = InputBudget(self.settings.ai_max_input_tokens)
        if len(budget.encoder.encode(payload, disallowed_special=())) > budget.maximum:
            raise ToolBudgetExceeded()
        buffer = ""
        total = 0
        with tracing_context(enabled=False):
            async for chunk in self.model.astream(
                [SystemMessage(content=WRITER_PROMPT), HumanMessage(content=payload)],
                config={"callbacks": []},
            ):
                part = str(chunk.text)
                total += len(part)
                if total > 12000:
                    raise ToolBudgetExceeded()
                buffer += part
                if len(buffer) >= 48:
                    yield buffer
                    buffer = ""
            if buffer:
                yield buffer
