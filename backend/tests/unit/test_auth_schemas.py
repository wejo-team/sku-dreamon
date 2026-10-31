"""자체 인증 입력의 정규화와 계정 응답의 공개 필드 계약을 검증한다."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.auth import AccountResponse, Credentials, LoginId, SignupCredentials


def test_credentials_normalize_only_ascii_login_case_and_password_nfc() -> None:
    credentials = Credentials.model_validate(
        {"loginId": "  DreamOn01\t", "password": "  e\u0301" + "A" * 11 + "  "}
    )
    assert credentials.login_id == "dreamon01"
    assert credentials.password == "  é" + "A" * 11 + "  "
    assert credentials.password not in repr(credentials)
    assert "password" not in credentials.model_dump()


@pytest.mark.parametrize(
    "login_id",
    ["abc", "a" * 25, "dream_on", "dream-on", "dream on", "드림온01", "Kabc", 1234],
)
def test_login_id_rejects_invalid_characters_length_and_non_strings(
    login_id: object,
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(LoginId).validate_python(login_id)


@pytest.mark.parametrize(
    "password", ["a" * 7, "a" * 129, "e\u0301" * 7, 123456789012345]
)
def test_password_length_is_measured_after_normalization(password: object) -> None:
    with pytest.raises(ValidationError):
        Credentials.model_validate({"loginId": "validuser", "password": password})


@pytest.mark.parametrize("password", ["a" * 8, "가" * 128, " " * 15, "🚀" * 15])
def test_password_accepts_code_point_boundaries_without_composition_rules(
    password: str,
) -> None:
    assert (
        Credentials.model_validate(
            {"loginId": "validuser", "password": password}
        ).password
        == password
    )


@pytest.mark.parametrize(
    "password",
    [
        "abcdefg!",
        "1234567@",
        "é" * 7 + "!",
        "😀" * 8,
        "a" * 127 + "!",
    ],
)
def test_signup_accepts_eight_characters_with_a_symbol(password: str) -> None:
    credentials = SignupCredentials.model_validate(
        {"loginId": "validuser", "password": password}
    )
    assert credentials.password == password
    assert password not in repr(credentials)
    assert "password" not in credentials.model_dump()


@pytest.mark.parametrize(
    "password",
    [
        "abcdef!",
        "abcdefgh",
        "한글비밀번호입니다",
        "abcdefg ",
        "abcdefg\n",
        "e\u0301" * 6 + "!",
        "a" * 128 + "!",
    ],
)
def test_signup_rejects_short_passwords_and_missing_symbols(password: str) -> None:
    with pytest.raises(ValidationError):
        SignupCredentials.model_validate({"loginId": "validuser", "password": password})


def test_signup_normalizes_before_counting_without_changing_case() -> None:
    credentials = SignupCredentials.model_validate(
        {"loginId": "validuser", "password": "e\u0301" * 6 + "A!"}
    )
    assert credentials.password == "é" * 6 + "A!"


@pytest.mark.parametrize(
    "character",
    [
        "가",  # 완성형
        "\u1100",  # 조합 자모
        "ㄱ",  # 호환 자모
        "\ua960",  # 자모 확장 A
        "\ud7b0",  # 자모 확장 B
        "\uffa1",  # 반각 자모
        "\u302e",  # 한글 방점
        "\u321d",  # 괄호 한글 오전
        "\u327c",  # 원문자 한글 참고
        " ",
        "\t",
        "\n",
        "\r",
        "\u0085",
        "\u00a0",
        "\u1680",
        "\u2003",
        "\u2028",
        "\u2029",
        "\u202f",
        "\u205f",
        "\u3000",
        "\ufeff",
    ],
)
def test_signup_rejects_hangul_and_whitespace_without_changing_login(
    character: str,
) -> None:
    password = "Abcdefg!" + character
    with pytest.raises(ValidationError):
        SignupCredentials.model_validate({"loginId": "validuser", "password": password})
    assert Credentials(loginId="validuser", password=password).password == password


@pytest.mark.parametrize("password", [" abcdefg!", "abcdefg! ", "abcd efg!"])
def test_signup_rejects_spaces_instead_of_removing_them(password: str) -> None:
    with pytest.raises(ValidationError):
        SignupCredentials.model_validate({"loginId": "validuser", "password": password})


@pytest.mark.parametrize(
    "body",
    [
        {"login_id": "validuser", "password": "a" * 15},
        {"loginId": "validuser", "password": "a" * 15, "rememberMe": True},
    ],
)
def test_credentials_keep_the_exact_request_contract(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Credentials.model_validate(body)


def test_account_response_requires_real_profile_state_and_omits_credentials() -> None:
    account_id = uuid4()
    response = AccountResponse(
        id=account_id,
        login_id="validuser",
        has_profile=True,
        school_verification="unverified",
        created_at=datetime(2026, 10, 24, tzinfo=UTC),
    )
    assert response.model_dump(mode="json") == {
        "id": str(account_id),
        "loginId": "validuser",
        "hasProfile": True,
        "schoolVerification": "unverified",
        "createdAt": "2026-10-24T00:00:00Z",
    }
    with pytest.raises(ValidationError):
        AccountResponse.model_validate(response.model_dump(exclude={"has_profile"}))
