"""가짜 HTTP의 실제 Responses 어댑터로 가드·도구·첫 최종 토큰 경계를 검사한다."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.agents.factory import OpenAiAgentDriver
from app.agents.tools import SourceTools
from app.agents.tracing import AiTracing
from app.agents.types import RecommendationPlan
from app.core.config import Settings
from app.services.ai_sources import SourceReader


def response(response_id: str, output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": response_id,
        "object": "response",
        "created_at": 1,
        "model": "gpt-6-luna",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": output,
        "usage": {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def message(message_id: str, text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "id": message_id,
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def text_events(
    item: dict[str, Any], parts: list[str], *, output_index: int
) -> list[dict[str, Any]]:
    return [
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {**item, "content": []},
        },
        *[
            {
                "type": "response.output_text.delta",
                "output_index": output_index,
                "content_index": 0,
                "item_id": item["id"],
                "delta": part,
            }
            for part in parts
        ],
        {
            "type": "response.output_text.done",
            "output_index": output_index,
            "content_index": 0,
            "item_id": item["id"],
            "text": "".join(parts),
        },
    ]


class ResponseStream(httpx.AsyncByteStream):
    def __init__(
        self,
        events: list[dict[str, Any]],
        release: asyncio.Event | None = None,
    ) -> None:
        self.events, self.release = events, release
        self.finished = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for item in self.events:
            yield (
                f"event: {item['type']}\ndata: "
                f"{json.dumps(item, ensure_ascii=False)}\n\n"
            ).encode()
            if self.release is not None and item.get("delta") == "첫 토큰":
                await self.release.wait()
        self.finished = True


async def test_native_responses_guard_gate_and_first_final_text() -> None:
    requests: list[dict[str, Any]] = []
    release = asyncio.Event()
    final_stream: ResponseStream | None = None
    plan = RecommendationPlan(intent="clarify", selections=[], guidance="조건 확인")

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal final_stream
        # MockTransport가 모든 HTTP 요청을 처리하므로 외부 제공자를 호출하지 않는다.
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer unit-test-key"
        body = json.loads(request.content)
        requests.append(body)
        index = len(requests)
        response_id = f"resp_{index}"
        events: list[dict[str, Any]] = [
            {"type": "response.created", "response": response(response_id, [])}
        ]
        if index == 1:
            reasoning: dict[str, Any] = {
                "type": "reasoning",
                "id": "rs_guard",
                "summary": [],
            }
            decision = message("msg_guard", '{"reason":"allowed"}')
            output = [reasoning, decision]
            events.append(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": reasoning,
                }
            )
            events.extend(
                text_events(decision, ['{"reason":', '"allowed"}'], output_index=1)
            )
        elif index == 2:
            intermediate = message("msg_read", "숨길 중간 발화")
            prepare = {
                "type": "function_call",
                "id": "fc_prepare",
                "call_id": "call_prepare",
                "name": "prepare_recommendations",
                "arguments": json.dumps({"plan": plan.model_dump()}),
                "status": "completed",
            }
            output = [intermediate, prepare]
            events.extend(text_events(intermediate, ["숨길 중간 발화"], output_index=0))
            events.extend(
                [
                    {
                        "type": "response.output_item.added",
                        "output_index": 1,
                        "item": {**prepare, "arguments": ""},
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": prepare["id"],
                        "output_index": 1,
                        "delta": prepare["arguments"],
                    },
                    {
                        "type": "response.output_item.done",
                        "output_index": 1,
                        "item": prepare,
                    },
                ]
            )
        else:
            assert index == 3
            reasoning = {
                "type": "reasoning",
                "id": "rs_final",
                "summary": [{"type": "summary_text", "text": "숨길 내부 추론"}],
            }
            answer = message("msg_final", "첫 토큰 다음")
            output = [reasoning, answer]
            events.append(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": reasoning,
                }
            )
            events.extend(text_events(answer, ["첫 토큰", " 다음"], output_index=1))
        events.append(
            {"type": "response.completed", "response": response(response_id, output)}
        )
        stream = ResponseStream(events, release if index == 3 else None)
        if index == 3:
            final_stream = stream
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=stream
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        # 실제 키나 환경 파일 없이 운영 어댑터의 직렬화·청크 변환만 실행한다.
        driver = object.__new__(OpenAiAgentDriver)
        driver.settings = Settings(
            openai_api_key=SecretStr("unit-test-key"), _env_file=None
        )
        driver.tracing = AiTracing(driver.settings)
        driver.model = ChatOpenAI(
            model="gpt-6-luna",
            api_key="unit-test-key",
            use_responses_api=True,
            use_previous_response_id=False,
            store=False,
            reasoning={"effort": "low"},
            max_retries=0,
            http_async_client=client,
        )
        reader = Mock(spec=SourceReader)
        reader.context = Mock(purpose="chat")
        sources = SourceTools(reader, max_sources=30, max_calls=8)
        gate, previous = AsyncMock(), AsyncMock(return_value=[])
        stream = driver.stream(sources, "이용 방법을 알려줘", [], previous, gate=gate)
        try:
            assert await asyncio.wait_for(anext(stream), 3) == "첫 토큰"
            assert final_stream is not None and not final_stream.finished
            gate.assert_awaited_once_with(plan)
            previous.assert_awaited_once()
            release.set()
            assert [value async for value in stream] == [" 다음"]
            assert final_stream.finished
        finally:
            release.set()
            await stream.aclose()

    guard, reading, final = requests
    # 이벤트 콜백이 있는 실제 ChatOpenAI는 분류용 ainvoke도 스트리밍한다.
    assert guard["stream"] is True
    assert not guard.get("tools")
    assert guard["text"]["format"]["name"] == "input_guard_decision"
    assert guard["text"]["format"]["strict"] is True
    assert reading["tool_choice"] == "required"
    assert reading["parallel_tool_calls"] is False
    assert {item["name"] for item in reading["tools"]} == {
        "find_people",
        "search_people_by_name",
        "find_contests",
        "search_contests_by_title",
        "find_teams",
        "search_teams_by_name",
        "get_resource_detail",
        "prepare_recommendations",
    }
    assert not final.get("tools")
    assert "tool_choice" not in final
    assert all(value["store"] is False for value in requests)
    assert all("previous_response_id" not in value for value in requests)
