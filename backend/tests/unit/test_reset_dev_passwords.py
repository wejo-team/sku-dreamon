"""개발 비밀번호의 차단 목록 검증이 DB 접근보다 먼저 수행되는지 검사한다."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts import reset_dev_passwords as reset


@pytest.mark.parametrize(
    "password", ["dreamon123", "dream on!", "드림온dreamon!", "dream!"]
)
def test_new_password_uses_signup_rules_before_reading_blocklist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, password: str
) -> None:
    monkeypatch.setattr(reset, "DEV_PASSWORD", password)
    with pytest.raises(ValidationError):
        reset.validate_password(tmp_path / "not-read.txt", "test")


async def test_blocked_password_fails_before_database_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "blocklist.txt"
    source.write_text(reset.DEV_PASSWORD + "\n", encoding="utf-8")

    def forbidden_database(url: str) -> None:
        pytest.fail("차단된 비밀번호로 DB에 접근하면 안 됩니다.")

    monkeypatch.setattr(reset, "create_database", forbidden_database)
    with pytest.raises(ValueError, match="차단 목록에 포함"):
        await reset.run(blocklist=source, blocklist_version="test", apply=True)


def test_validated_password_uses_full_value_and_records_exact_source_hash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blocklist.txt"
    source.write_text("dreamon\n12345678\n", encoding="utf-8")
    credentials, checksum = reset.validate_password(source, "test")

    assert credentials.password == reset.DEV_PASSWORD
    assert checksum == hashlib.sha256(source.read_bytes()).hexdigest()
    assert reset.DEV_PASSWORD not in repr(credentials)
