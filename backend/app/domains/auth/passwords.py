"""정규화된 비밀번호의 Argon2id 처리와 외부 차단 목록 로딩을 제공한다."""

import asyncio
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError

# 라이브러리 기본값 변경과 무관하게 검증한 비용을 사용한다. 비용 변경 후에는
# 로그인에서 needs_password_rehash를 확인해 다음 저장에 새 해시를 적용한다.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


async def hash_password(password: str) -> str:
    """입력 DTO가 NFC·길이를 검증한 전체 값을 이벤트 루프 밖에서 해시한다."""
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    """오입력은 False, 저장 해시 손상·검증기 장애는 예외로 구분한다.

    password_hash는 서버 저장소에서 읽은 값만 전달한다. 입력의 NFC·길이
    검증은 DTO에서 완료하며 여기서 공백 제거·잘라내기·재정규화하지 않는다.
    """
    try:
        return await asyncio.to_thread(_hasher.verify, password_hash, password)
    except VerifyMismatchError:
        return False


def needs_password_rehash(password_hash: str) -> bool:
    """성공한 검증 뒤 저장 해시의 알고리즘·비용 갱신 필요 여부를 확인한다."""
    return _hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class PasswordBlocklist:
    """공급자가 준비한 목록의 버전과 전체 비밀번호 비교 집합을 유지한다."""

    version: str
    _passwords: frozenset[str] = field(repr=False)

    @classmethod
    def from_file(cls, path: Path, *, version: str) -> "PasswordBlocklist":
        """UTF-8의 한 줄 한 비밀번호 파일을 앱 초기화 시 읽는다.

        LF·CRLF 구분자만 제거하고 양끝 공백과 대소문자를 보존한다. 파일에
        줄바꿈이 포함된 비밀번호는 표현하지 않는다. 비어 있거나 읽지 못한
        목록은 오류로 처리하며, 예시 목록이나 외부 네트워크를 대신 사용하지
        않는다. 운영 공급·갱신과 설정 연결은 호출자가 담당한다.
        """
        if not version.strip():
            raise ValueError("password blocklist version is required")
        entries = path.read_bytes().decode("utf-8").split("\n")
        passwords = frozenset(
            unicodedata.normalize("NFC", entry.removesuffix("\r"))
            for entry in entries
            if entry.removesuffix("\r")
        )
        if not passwords:
            raise ValueError("password blocklist must not be empty")
        return cls(version=version, _passwords=passwords)

    def contains(self, password: str) -> bool:
        """일부 단어의 포함 여부가 아니라 NFC를 적용한 전체 값만 비교한다."""
        return unicodedata.normalize("NFC", password) in self._passwords
