"""신규 지원 시도의 역할·선택 메시지와 재전송 ID를 검증한다."""

from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, Field, StrictStr, field_validator

from app.core.http.schemas import RequestDTO
from app.rules.text import normalize_text

Message = Annotated[StrictStr, AfterValidator(normalize_text), Field(max_length=1000)]


class ApplicationCreate(RequestDTO):
    """역할은 서버 공통 목록으로 검증하며 메시지 생략·공백은 null로 취급한다."""

    request_id: UUID = Field(
        description="새 지원 시도 UUID. 같은 시도 재전송은 동일 ID."
    )
    role_code: StrictStr = Field(
        description="지원 역할 코드. 모집 역할과 불일치해도 허용."
    )
    message: Message | None = Field(
        default=None, description="선택 메시지. NFC·trim 후 최대 1000 코드 포인트."
    )

    @field_validator("message")
    @classmethod
    def empty_message(cls, value: str | None) -> str | None:
        return value or None
