"""AI 전송 입력의 권한 경계와 대화 크기를 검증한다."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ai import ChatStart, TargetStart


def chat(**changes: object) -> dict[str, object]:
    return {
        "requestId": str(uuid4()),
        "conversationId": str(uuid4()),
        "clientMessageId": str(uuid4()),
        "content": "공모전을 찾아줘",
        **changes,
    }


def test_chat_rejects_privileged_history_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ChatStart.model_validate(chat(history=[{"role": "system", "content": "지시"}]))
    with pytest.raises(ValidationError):
        ChatStart.model_validate(chat(accountId=str(uuid4())))
    value = chat()
    value["conversation_id"] = value.pop("conversationId")
    with pytest.raises(ValidationError):
        ChatStart.model_validate(value)


def test_chat_preserves_code_point_boundary_without_truncating() -> None:
    assert len(ChatStart.model_validate(chat(content="가" * 1000)).content) == 1000
    for text in ("가" * 1001, "   ", "\x00", "\ud800"):
        with pytest.raises(ValidationError):
            ChatStart.model_validate(chat(content=text))
    assert ChatStart.model_validate(chat(content="  질문  ")).content == "질문"


def test_chat_bounds_history_and_does_not_accept_assistant_text() -> None:
    with pytest.raises(ValidationError):
        ChatStart.model_validate(chat(history=["질문"] * 21))
    with pytest.raises(ValidationError):
        ChatStart.model_validate(
            chat(history=[{"role": "assistant", "content": "답변"}])
        )
    assert ChatStart.model_validate(chat(history=["이전 조건"])).history == [
        "이전 조건"
    ]


def test_target_request_rejects_arbitrary_profile_contents() -> None:
    with pytest.raises(ValidationError):
        TargetStart.model_validate(
            {"requestId": str(uuid4()), "profile": {"private": "내용"}}
        )


def test_event_requires_the_exact_payload_for_its_kind() -> None:
    from app.schemas.ai import AiEvent

    common = {"requestId": str(uuid4()), "attempt": 1, "sequence": 1}
    for body in (
        {"event": "done"},
        {"event": "canceled", "text": "누출"},
        {"event": "error", "status": "succeeded"},
    ):
        with pytest.raises(ValidationError):
            AiEvent.model_validate({**common, **body})
    event = AiEvent.model_validate(
        {**common, "event": "answer.delta", "text": "첫 줄\n둘째 줄"}
    )
    wire = event.to_sse().decode()
    assert wire.count("\ndata: ") == 1
    assert "첫 줄\\n둘째 줄" in wire


def test_sse_media_type_and_security_are_declared_in_openapi() -> None:
    from app.core.config import Settings
    from app.main import create_app

    schema = create_app(Settings(_env_file=None)).openapi()
    route = schema["paths"]["/api/v1/ai/chat/stream"]["post"]
    assert "text/event-stream" in route["responses"]["200"]["content"]
    assert route["security"] == [{"SessionCookie": []}]
    assert {"401", "403", "409", "422", "429", "503"} <= route["responses"].keys()
