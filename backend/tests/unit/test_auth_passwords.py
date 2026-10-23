"""비밀번호 전체 값 검증과 버전이 지정된 차단 목록의 비교를 확인한다."""

from pathlib import Path
from threading import get_ident

import pytest
from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import InvalidHashError

from app.domains.auth.passwords import (
    PasswordBlocklist,
    hash_password,
    needs_password_rehash,
    verify_password,
)


async def test_hash_uses_argon2id_and_unique_salts() -> None:
    password = "  비밀번호 전체를 보존합니다 A  "

    first = await hash_password(password)
    second = await hash_password(password)

    assert first != second
    parameters = extract_parameters(first)
    assert parameters.type is Type.ID
    assert parameters.memory_cost == 19456
    assert parameters.time_cost == 2
    assert parameters.parallelism == 1
    assert await verify_password(first, password)
    assert not await verify_password(first, password.strip())
    assert not await verify_password(first, password.lower())
    assert not needs_password_rehash(first)


async def test_verification_compares_the_entire_unicode_password() -> None:
    password = "가" * 127 + "A"
    stored = await hash_password(password)

    assert await verify_password(stored, password)
    assert not await verify_password(stored, "가" * 127 + "B")


async def test_damaged_stored_hash_is_not_treated_as_a_password_mismatch() -> None:

    with pytest.raises(InvalidHashError):
        await verify_password("not-an-argon2-hash", "a sufficiently long password")


def test_changed_parameters_request_rehash() -> None:
    old_hash = PasswordHasher(time_cost=1, memory_cost=19456, parallelism=1).hash(
        "a sufficiently long password"
    )

    assert needs_password_rehash(old_hash)


async def test_expensive_hash_and_verify_run_outside_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop_thread = get_ident()

    def hash_on_worker(self: PasswordHasher, password: str) -> str:
        assert get_ident() != event_loop_thread
        return "stored-hash"

    def verify_on_worker(
        self: PasswordHasher, password_hash: str, password: str
    ) -> bool:
        assert get_ident() != event_loop_thread
        return True

    monkeypatch.setattr(PasswordHasher, "hash", hash_on_worker)
    monkeypatch.setattr(PasswordHasher, "verify", verify_on_worker)

    assert await hash_password("a sufficiently long password") == "stored-hash"
    assert await verify_password("stored-hash", "a sufficiently long password")


def test_blocklist_preserves_spaces_and_matches_only_whole_normalized_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "passwords.txt"
    source.write_bytes(
        "  흔한 비밀번호입니다 A  \r\ncafe\u0301 password example\n".encode()
    )

    blocklist = PasswordBlocklist.from_file(source, version="test-2026-10")

    assert blocklist.version == "test-2026-10"
    assert blocklist.contains("  흔한 비밀번호입니다 A  ")
    assert not blocklist.contains("흔한 비밀번호입니다 A")
    assert not blocklist.contains("prefix   흔한 비밀번호입니다 A  ")
    assert blocklist.contains("café password example")
    assert blocklist.contains("cafe\u0301 password example")
    assert not blocklist.contains("CAFÉ password example")
    assert "흔한" not in repr(blocklist)


@pytest.mark.parametrize("content", ["", "\n\r\n"])
def test_empty_blocklist_is_rejected(tmp_path: Path, content: str) -> None:
    source = tmp_path / "empty.txt"
    source.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        PasswordBlocklist.from_file(source, version="test-empty")


def test_blocklist_requires_a_version(tmp_path: Path) -> None:
    source = tmp_path / "passwords.txt"
    source.write_text("a sufficiently long password\n", encoding="utf-8")

    with pytest.raises(ValueError, match="version"):
        PasswordBlocklist.from_file(source, version="  ")
