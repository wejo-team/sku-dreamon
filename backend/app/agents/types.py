"""모델 입력과 서버가 검증하는 내부 자료·후보 타입을 정의한다."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ai import (
    AiPurpose,
    AssessmentInformationStatus,
    AssessmentKey,
    AssessmentOverview,
    AssessmentQuestion,
    AssessmentScore,
    AssessmentSummary,
    Evidence,
    ResourceKind,
)
from app.services.sessions import SessionPrincipal


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ResourceKind
    resource_id: UUID
    fingerprint: str
    account_id: UUID | None = None
    team_id: UUID | None = None
    contest_id: UUID | None = None
    profile_version: str | None = None

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.resource_id}"


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: Reference
    title: str
    is_demo: bool
    field_codes: list[str] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)
    facts: dict[str, object]
    is_selection_candidate: bool = False

    def model_input(self) -> dict[str, object]:
        return {"key": self.reference.key, "title": self.title, "facts": self.facts}


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(description="조회 도구가 반환한 실제 key 그대로")
    reason: str = Field(
        max_length=500, description="조회된 사실과 사용자 조건에 근거한 이유"
    )
    evidence: Evidence = Field(
        description="실제 조회 자료에서 확인한 근거, 각 500자 이내"
    )


class RecommendationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["recommend", "clarify", "empty"]
    selections: list[Selection] = Field(max_length=30)
    guidance: str = Field(
        max_length=1000, description="사용자에게 설명할 조건 또는 확인 질문"
    )


class AssessmentCriterionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: AssessmentKey
    score: AssessmentScore | None
    information_status: AssessmentInformationStatus = Field(alias="informationStatus")
    summary: AssessmentSummary
    evidence_refs: list[str] = Field(alias="evidenceRefs", max_length=6)

    @model_validator(mode="after")
    def require_score_information(self) -> Self:
        if (self.information_status == "sufficient") != (self.score is not None):
            raise ValueError("자료가 충분한 항목만 숫자 점수를 제공할 수 있습니다.")
        if self.score is not None and not self.evidence_refs:
            raise ValueError("점수가 있는 항목에는 등록 근거가 필요합니다.")
        return self


class ApplicantAssessmentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    criteria: list[AssessmentCriterionPlan] = Field(min_length=4, max_length=4)
    questions: list[AssessmentQuestion] = Field(max_length=3)

    @model_validator(mode="after")
    def require_all_criteria(self) -> Self:
        if len({item.key for item in self.criteria}) != 4:
            raise ValueError("평가 항목은 종류별로 한 번씩 필요합니다.")
        return self


class ApplicantAssessmentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: AssessmentOverview
    assessments: list[ApplicantAssessmentSelection] = Field(max_length=3)


@dataclass(frozen=True)
class AgentContext:
    principal: SessionPrincipal
    purpose: AiPurpose
    team_id: UUID | None = None
    application_id: UUID | None = None


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


RecommendationGate = Callable[[RecommendationPlan], Awaitable[None]]
PreviousContext = Callable[[], Awaitable[list[dict[str, object]]]]
