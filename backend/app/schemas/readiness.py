"""내부 준비 검사에서도 민감한 세부 원인을 노출하지 않는 상태를 정의한다."""

from typing import Literal

from pydantic import BaseModel


class ReadinessResponse(BaseModel):
    status: Literal["ready", "unavailable"]
