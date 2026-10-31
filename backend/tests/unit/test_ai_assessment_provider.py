"""실제 Responses 어댑터의 평가 JSON·도구·완료 상태를 외부 호출 없이 검사한다."""

import json
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.agents.factory import OpenAiAgentDriver
from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.tracing import AiTracing
from app.core.config import Settings
from app.services.ai_sources import SourceReader
from tests.unit.test_ai_assessment import applicant, output_data
from tests.unit.test_ai_provider import message, response


@pytest.mark.parametrize(
    ("status", "reason", "error"),
    [
        ("completed", None, None),
        ("incomplete", "max_output_tokens", ToolBudgetExceeded),
        ("incomplete", "content_filter", ValueError),
    ],
)
async def test_assessment_uses_native_strict_json_and_rejects_incomplete_provider(
    status: str, reason: str | None, error: type[Exception] | None
) -> None:
    source = applicant()
    output = output_data(source)
    output["assessments"][0]["criteria"][0].update(
        score=75, informationStatus="sufficient", evidenceRefs=["application.role"]
    )
    requests: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/responses"
        body = json.loads(request.content)
        requests.append(body)
        assert not body.get("stream", False)
        if len(requests) == 1:
            result = response(
                "resp_read",
                [
                    {
                        "type": "function_call",
                        "id": "fc_read",
                        "call_id": "call_read",
                        "name": "read_applicant",
                        "arguments": "{}",
                        "status": "completed",
                    }
                ],
            )
        else:
            assert len(requests) == 2
            result = response(
                "resp_assessment",
                [message("msg_assessment", json.dumps(output, ensure_ascii=False))],
            )
            result["status"] = status
            result["incomplete_details"] = (
                None if reason is None else {"reason": reason}
            )
        return httpx.Response(200, json=result)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
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
            max_retries=0,
            http_async_client=client,
        )
        reader = Mock(spec=SourceReader)
        reader.context = Mock(
            purpose="applicant_review", application_id=source.reference.resource_id
        )
        reader.get = AsyncMock(return_value=source)
        sources = SourceTools(reader, max_sources=30, max_calls=8)
        if error is None:
            result = await driver.assess(sources)
            assert result.assessments[0].criteria[0].score == 75
            assert result.assessments[0].criteria[1].score is None
        else:
            with pytest.raises(error):
                await driver.assess(sources)

    assert len(requests) == 2 and sources.calls == 1
    for request in requests:
        assert request["text"]["format"]["type"] == "json_schema"
        assert request["text"]["format"]["strict"] is True
        assert request["text"]["format"]["name"] == "ApplicantAssessmentPlan"
        assert {tool["name"] for tool in request["tools"]} == {"read_applicant"}
        assert request["store"] is False
        assert "previous_response_id" not in request
    assert '"evidence"' in json.dumps(requests[1], ensure_ascii=False).replace(
        '\\"', '"'
    )
    assert "application.role" in str(requests[1])
