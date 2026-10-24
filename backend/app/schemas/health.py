"""health API의 고정 응답 형식을 정의한다."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """애플리케이션의 기본 응답 상태."""

    status: Literal["ok"] = Field(
        default="ok",
        description=(
            "프로세스 응답 상태. ok는 기본 응답 성공을 나타내며 "
            "DB 준비 상태를 검사하지 않습니다."
        ),
    )
