"""AI 카드의 사실 출처·타입·버전과 표시 결과의 무결성을 검사한다."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.types import (
    AgentContext,
    RecommendationPlan,
    Reference,
    Resource,
    Selection,
)
from app.schemas.ai import (
    AiEvent,
    ChatStart,
    RichResourceCard,
    ValidateResult,
)
from app.services.ai import build_result
from app.services.ai_runs import Execution
from app.services.sessions import SessionPrincipal


def profile_facts() -> dict[str, object]:
    return {
        "skillCodes": ["ui_ux"],
        "weeklyAvailabilityCode": None,
        "experienceState": "unspecified",
        "experienceBody": None,
        "introduction": "프로젝트에 함께하고 싶어요.",
        "privateToken": "must-never-appear",
    }


def execution() -> Execution:
    now = datetime.now(UTC)
    request_id = uuid4()
    principal = SessionPrincipal(
        uuid4(), uuid4(), b"test-token-hash", now + timedelta(hours=1)
    )
    context = AgentContext(principal=principal, purpose="chat")
    payload = ChatStart.model_validate(
        {
            "requestId": str(request_id),
            "conversationId": str(uuid4()),
            "clientMessageId": str(uuid4()),
            "content": "등록한 정보를 비교해줘",
            "resultFormat": "rich",
        }
    )
    return Execution(request_id, 1, context, payload)


def test_profile_display_is_typed_from_authorized_facts() -> None:
    resource_id = uuid4()
    facts = profile_facts()
    source = Resource(
        reference=Reference(
            kind="person",
            resource_id=resource_id,
            account_id=uuid4(),
            profile_version="2",
            fingerprint="a" * 64,
        ),
        title="등록 사용자",
        is_demo=False,
        field_codes=["design"],
        role_codes=["design"],
        facts=facts,
        is_selection_candidate=True,
    )
    plan = RecommendationPlan(
        intent="recommend",
        selections=[
            Selection(
                key=source.reference.key,
                reason="등록 정보 참고",
                evidence=["UI/UX 역량 등록"],
            )
        ],
        guidance="등록 정보를 확인하세요.",
    )
    result = build_result(execution(), plan, [source], "요약")
    wire = result.model_dump(mode="json")
    assert "schemaVersion" not in wire
    shown = wire["cards"][0]
    assert shown["title"] == "등록 사용자"
    assert shown["fieldCodes"] == ["design"]
    assert shown["roleCodes"] == ["design"]
    assert shown["evidence"] == ["UI/UX 역량 등록"]
    details = shown["details"]
    assert details == {
        "kind": "person",
        **{key: value for key, value in facts.items() if key != "privateToken"},
    }
    assert "must-never-appear" not in result.model_dump_json()
    assert (
        ValidateResult.model_validate({"attempt": 1, "result": wire}).result == result
    )
    event = AiEvent(
        event="result", request_id=uuid4(), attempt=1, sequence=1, result=result
    )
    serialized = json.loads(event.to_sse().decode().split("\ndata: ", 1)[1])
    assert set(serialized) == {"requestId", "attempt", "sequence", "result"}
    assert (
        ValidateResult.model_validate(
            {"attempt": 1, "result": serialized["result"]}
        ).result
        == result
    )


def test_card_rejects_mismatched_type_and_unregistered_skill() -> None:
    details = {
        "kind": "person",
        **{
            key: value
            for key, value in profile_facts().items()
            if key != "privateToken"
        },
    }
    data = {
        "kind": "person",
        "resourceId": str(uuid4()),
        "title": "사용자",
        "reason": "근거",
        "fieldCodes": [],
        "roleCodes": [],
        "isDemo": False,
        "evidence": [],
        "details": details,
    }
    assert RichResourceCard.model_validate(data).kind == "person"
    with pytest.raises(ValidationError):
        RichResourceCard.model_validate({**data, "kind": "team"})
    with pytest.raises(ValidationError):
        RichResourceCard.model_validate(
            {**data, "details": {**details, "skillCodes": ["invented_skill"]}}
        )


def test_legacy_request_and_result_keep_their_wire_shape_and_hash() -> None:
    payload = {
        "requestId": str(uuid4()),
        "conversationId": str(uuid4()),
        "clientMessageId": str(uuid4()),
        "content": "사람 추천",
        "history": [],
        "previousResults": [],
    }
    request = ChatStart.model_validate(payload)
    assert request.model_dump(mode="json") == payload
    source = Resource(
        reference=Reference(kind="person", resource_id=uuid4(), fingerprint="a" * 64),
        title="이전 공개 카드",
        is_demo=False,
        facts={},
    )
    run = execution()
    run = Execution(run.request_id, run.attempt, run.context, request)
    plan = RecommendationPlan(
        intent="recommend",
        guidance="",
        selections=[
            Selection(key=source.reference.key, reason="등록 조건", evidence=[])
        ],
    )
    result = build_result(run, plan, [source], "기존 답변")
    card = result.model_dump(mode="json")["cards"][0]
    assert set(card) == {
        "kind",
        "resourceId",
        "title",
        "reason",
        "fieldCodes",
        "roleCodes",
        "isDemo",
    }
    assert (
        ValidateResult.model_validate(
            {"attempt": 1, "result": result.model_dump(mode="json")}
        ).result
        == result
    )


@pytest.mark.parametrize(
    ("kind", "facts"),
    [
        (
            "contest",
            {
                "organizer": "등록 주최자",
                "registrationStatus": "scheduled",
                "startsAt": "2026-11-01T00:00:00Z",
                "endsAt": "2026-11-30T00:00:00Z",
            },
        ),
        (
            "team",
            {
                "contestTitle": "등록 공모전",
                "capacity": "4",
                "memberCount": 2,
                "recruitmentEndsAt": "2026-11-30T00:00:00Z",
                "isRecruiting": True,
            },
        ),
    ],
)
def test_nonprofile_card_details_preserve_registered_types(
    kind: str, facts: dict[str, object]
) -> None:
    source = Resource.model_validate(
        {
            "reference": {
                "kind": kind,
                "resource_id": uuid4(),
                "fingerprint": "b" * 64,
            },
            "title": "등록 이름",
            "is_demo": False,
            "facts": {**facts, "notForDisplay": "private"},
        }
    )
    plan = RecommendationPlan(
        intent="recommend",
        selections=[
            Selection(key=source.reference.key, reason="조회 이유", evidence=[])
        ],
        guidance="",
    )
    wire = build_result(execution(), plan, [source], "요약").model_dump(mode="json")
    assert wire["cards"][0]["details"] == {"kind": kind, **facts}
    assert "notForDisplay" not in str(wire)
    card = wire["cards"][0]
    field = "memberCount" if kind == "team" else "startsAt"
    malformed = {
        **card,
        "details": {**card["details"], field: "2" if kind == "team" else "2026-11-01"},
    }
    with pytest.raises(ValidationError):
        RichResourceCard.model_validate(malformed)


def test_wire_validation_rejects_nested_snake_case_and_excessive_evidence() -> None:
    card = {
        "kind": "person",
        "resourceId": str(uuid4()),
        "title": "사용자",
        "reason": "이유",
        "fieldCodes": [],
        "roleCodes": [],
        "isDemo": False,
        "evidence": [],
        "details": {
            "kind": "person",
            **{
                key: value
                for key, value in profile_facts().items()
                if key != "privateToken"
            },
        },
    }
    result = {
        "kind": "chat",
        "answer": "요약",
        "cards": [card],
        "generatedAt": "2026-10-31T00:00:00Z",
    }
    valid = ValidateResult.model_validate({"attempt": 1, "result": result})
    wire = valid.result.model_dump(mode="json")
    wire["cards"][0]["details"]["weekly_availability_code"] = wire["cards"][0][
        "details"
    ].pop("weeklyAvailabilityCode")
    with pytest.raises(ValidationError):
        ValidateResult.model_validate({"attempt": 1, "result": wire})
    for evidence in (["근거"] * 7, ["가" * 501]):
        with pytest.raises(ValidationError):
            RichResourceCard.model_validate({**card, "evidence": evidence})


def test_model_selection_limits_evidence_before_answer_generation() -> None:
    assert Selection(key="person:public", reason="이유", evidence=["가" * 500])
    with pytest.raises(ValidationError):
        Selection(key="person:public", reason="이유", evidence=["가" * 501])
    assert (
        Selection.model_json_schema()["properties"]["evidence"]["items"]["maxLength"]
        == 500
    )
