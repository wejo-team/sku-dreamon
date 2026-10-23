"""아이디·비밀번호 입력 규칙과 본인 계정의 응답 필드를 정의한다."""

import string
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, StrictStr

from app.core.http.schemas import RequestDTO, ResponseDTO, Timestamp

_ASCII_LOWERCASE = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def normalize_login_id(value: str) -> str:
    """앞뒤 공백과 ASCII 대소문자만 같은 아이디로 취급한다."""
    return value.strip().translate(_ASCII_LOWERCASE)


def normalize_password(value: str) -> str:
    """대소문자·공백을 보존한 채 NFC만 적용한다."""
    normalized = unicodedata.normalize("NFC", value)
    # JSON의 고립 surrogate는 유효한 Unicode 문자열이 아니며 해시기가
    # 처리할 수 없다. 해시 단계의 500 대신 요청 검증의 422로 거부한다.
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("Password must contain valid Unicode characters") from error
    return normalized


LoginId = Annotated[
    StrictStr,
    AfterValidator(normalize_login_id),
    Field(min_length=4, max_length=24, pattern=r"^[a-z0-9]{4,24}$"),
]
Password = Annotated[
    StrictStr,
    AfterValidator(normalize_password),
    Field(min_length=15, max_length=128),
]


class Credentials(RequestDTO):
    login_id: LoginId
    password: Password = Field(
        repr=False, exclude=True, json_schema_extra={"writeOnly": True}
    )


class AccountResponse(ResponseDTO):
    id: UUID
    login_id: LoginId
    is_demo: bool
    has_profile: bool
    school_verification: Literal["unverified"]
    created_at: Timestamp


class AuthResult(ResponseDTO):
    account: AccountResponse


class LoginIdAvailability(ResponseDTO):
    normalized_login_id: LoginId
    available: bool
