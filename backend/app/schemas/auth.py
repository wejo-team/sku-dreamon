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
    Field(
        min_length=4,
        max_length=24,
        pattern=r"^[a-z0-9]{4,24}$",
        description=(
            "로그인 아이디. 앞뒤 공백을 제거하고 ASCII 영문 대문자를 소문자로 "
            "변환한 뒤 영문 소문자와 숫자로 이루어진 4~24자인지 검사합니다."
        ),
        examples=["dreamon01"],
    ),
]
Password = Annotated[
    StrictStr,
    AfterValidator(normalize_password),
    Field(
        min_length=15,
        max_length=128,
        description=(
            "비밀번호. NFC 정규화 후 Unicode 코드 포인트 기준 15~128자이며, "
            "대소문자와 앞뒤·중간 공백을 보존합니다. 요청 전용 필드입니다."
        ),
    ),
]


class Credentials(RequestDTO):
    """회원가입과 로그인에 사용하는 아이디·비밀번호 입력."""

    login_id: LoginId
    password: Password = Field(
        repr=False, exclude=True, json_schema_extra={"writeOnly": True}
    )


class AccountResponse(ResponseDTO):
    """로그인한 본인에게 제공하는 계정 정보."""

    id: UUID = Field(description="로그인 아이디와 별개로 계정을 식별하는 UUID.")
    login_id: LoginId = Field(
        description=(
            "정규화된 로그인 아이디. ASCII 영문 소문자와 숫자로 이루어진 4~24자."
        )
    )
    has_profile: bool = Field(description="저장된 프로필의 존재 여부.")
    school_verification: Literal["unverified"] = Field(
        description="학교 인증 상태. 현재는 미인증을 나타내는 unverified만 사용합니다."
    )
    created_at: Timestamp = Field(
        description="계정 생성 시각. UTC 기준이며 Z로 끝나는 ISO 8601 문자열."
    )


class AuthResult(ResponseDTO):
    """회원가입·로그인 성공 시 반환하는 본인 계정 정보."""

    account: AccountResponse = Field(
        description="가입하거나 로그인한 본인의 계정 정보."
    )


class LoginIdAvailability(ResponseDTO):
    """정규화된 로그인 아이디의 사용 가능 여부."""

    normalized_login_id: LoginId = Field(
        description=(
            "중복 확인 대상 아이디에서 앞뒤 공백을 제거하고 "
            "ASCII 영문 대문자를 소문자로 변환한 값."
        )
    )
    available: bool = Field(
        description=(
            "조회 시점의 아이디 사용 가능 여부. 가입 예약을 의미하지 않으며 "
            "가입 시 중복 여부를 다시 확인합니다."
        )
    )


class CsrfToken(ResponseDTO):
    """현재 익명 상태 또는 로그인 세션에 결합된 CSRF 보호 토큰."""

    csrf_token: str = Field(
        description=(
            "상태 변경 요청의 CSRF 헤더에 전달할 토큰. "
            "현재 익명 상태 또는 로그인 세션에 결합됩니다."
        )
    )
