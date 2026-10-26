"""AI 요청·결과·스트림 이벤트와 원문 없는 실행 상태를 정의한다."""

import unicodedata
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, Field, StrictStr, field_validator, model_validator

from app.core.http.schemas import (
    PositiveInt,
    RequestDTO,
    ResponseDTO,
    Timestamp,
    Version,
)

AiPurpose = Literal["chat", "applicant_review", "applicant_recommendation"]
AiStatus = Literal["pending", "succeeded", "empty", "failed", "canceled"]
ResourceKind = Literal["contest", "team", "person", "application"]


def normalize_message(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(value) <= 1000 or "\x00" in value:
        raise ValueError("메시지는 1~1,000자여야 합니다.")
    value.encode("utf-8")
    return value


MessageText = Annotated[StrictStr, AfterValidator(normalize_message)]


class PreviousResult(RequestDTO):
    request_id: UUID
    attempt: PositiveInt


class ChatStart(RequestDTO):
    request_id: UUID = Field(
        description="전송 전에 생성한 실행 ID. 유실된 요청 조회에도 사용."
    )
    conversation_id: UUID = Field(description="현재 탭의 대화 ID. 새 대화에서 교체.")
    client_message_id: UUID = Field(description="동일 사용자 메시지의 중복 방지 ID.")
    content: MessageText
    history: list[MessageText] = Field(default_factory=list, max_length=20)
    previous_results: list[PreviousResult] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bound_context(self) -> Self:
        if sum(map(len, self.history)) + len(self.content) > 12000:
            raise ValueError("대화가 길어졌습니다. 새 대화를 시작해 주세요.")
        return self


class TargetStart(RequestDTO):
    request_id: UUID


class RetryStart(RequestDTO):
    expected_attempt: PositiveInt
    input: ChatStart | TargetStart


class CancelRequest(RequestDTO):
    expected_attempt: PositiveInt


class ResourceCard(ResponseDTO):
    kind: Literal["contest", "team", "person"]
    resource_id: UUID
    title: str = Field(max_length=500)
    reason: str = Field(max_length=500)
    field_codes: list[str]
    role_codes: list[str]
    is_demo: bool


class ChatResult(ResponseDTO):
    kind: Literal["chat"] = "chat"
    answer: str = Field(max_length=12000)
    cards: list[ResourceCard] = Field(max_length=3)
    generated_at: Timestamp
    references_changed: bool = False


class ProfileVersion(ResponseDTO):
    account_id: UUID
    used_version: Version
    current_version: Version


class ApplicantReviewResult(ResponseDTO):
    kind: Literal["applicant_review"] = "applicant_review"
    application_id: UUID
    summary: str = Field(max_length=12000)
    evidence: list[Annotated[str, Field(max_length=500)]] = Field(max_length=6)
    profile_versions: list[ProfileVersion] = Field(min_length=1, max_length=1)
    is_stale: bool
    is_selection_candidate: bool
    generated_at: Timestamp


class ApplicantRecommendation(ResponseDTO):
    application_id: UUID
    reason: str = Field(max_length=500)
    profile_version: ProfileVersion


class ApplicantRecommendationResult(ResponseDTO):
    kind: Literal["applicant_recommendation"] = "applicant_recommendation"
    summary: str = Field(max_length=12000)
    candidates: list[ApplicantRecommendation] = Field(max_length=100)
    is_stale: bool
    generated_at: Timestamp


AiResult = Annotated[
    ChatResult | ApplicantReviewResult | ApplicantRecommendationResult,
    Field(discriminator="kind"),
]


class AiFailure(ResponseDTO):
    code: Literal[
        "temporary_failure", "invalid_output", "context_changed", "limit_exceeded"
    ]
    message: str
    retryable: bool


class AiRequestView(ResponseDTO):
    id: UUID
    purpose: AiPurpose
    conversation_id: UUID | None
    team_id: UUID | None
    application_id: UUID | None
    attempt: PositiveInt
    status: AiStatus
    failure: AiFailure | None
    expires_at: Timestamp


class ValidateResult(RequestDTO):
    attempt: PositiveInt
    result: AiResult

    @field_validator("result", mode="before")
    @classmethod
    def require_wire_names(cls, value: object) -> object:
        # 응답 DTO를 되돌려 받는 경로에서도 내부 snake_case 이름은 허용하지 않는다.
        def check(item: object) -> None:
            if isinstance(item, dict):
                for key, nested in item.items():
                    if not isinstance(key, str) or "_" in key:
                        raise ValueError("응답의 camelCase 필드명을 사용해 주세요.")
                    check(nested)
            elif isinstance(item, list):
                for nested in item:
                    check(nested)

        check(value)
        return value


class ResultValidation(ResponseDTO):
    valid: bool
    result: AiResult | None


class AiEvent(ResponseDTO):
    """이벤트 종류별 페이로드는 런타임에서 지정하고 JSON 스키마에도 노출한다."""

    event: Literal[
        "started",
        "progress",
        "answer.delta",
        "result",
        "done",
        "error",
        "canceled",
        "invalidated",
    ]
    request_id: UUID
    attempt: PositiveInt
    sequence: PositiveInt
    purpose: AiPurpose | None = None
    stage: Literal["searching", "validating", "writing"] | None = None
    text: str | None = None
    result: AiResult | None = None
    status: Literal["succeeded", "empty"] | None = None
    failure: AiFailure | None = None
    reason: Literal["context_changed"] | None = None

    @model_validator(mode="after")
    def require_event_payload(self) -> Self:
        required = {
            "started": {"purpose"},
            "progress": {"stage"},
            "answer.delta": {"text"},
            "result": {"result"},
            "done": {"status"},
            "error": {"failure"},
            "canceled": set(),
            "invalidated": {"reason"},
        }
        payload_fields = {
            "purpose",
            "stage",
            "text",
            "result",
            "status",
            "failure",
            "reason",
        }
        populated = {name for name in payload_fields if getattr(self, name) is not None}
        if populated != required[self.event]:
            raise ValueError("이벤트 종류와 페이로드가 일치하지 않습니다.")
        return self

    def to_sse(self) -> bytes:
        payload = self.model_dump_json(exclude={"event"}, exclude_none=True)
        return f"event: {self.event}\ndata: {payload}\n\n".encode()
