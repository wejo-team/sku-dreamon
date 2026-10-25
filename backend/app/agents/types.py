"""모델 입력과 서버가 검증하는 내부 자료·후보 타입을 정의한다."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai import AiPurpose, ResourceKind
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
    evidence: list[str] = Field(
        max_length=6, description="실제 조회 자료에서 확인한 근거"
    )


class RecommendationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Literal["recommend", "clarify", "empty"]
    selections: list[Selection] = Field(max_length=30)
    guidance: str = Field(
        max_length=1000, description="사용자에게 설명할 조건 또는 확인 질문"
    )


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
