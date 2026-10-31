"""한 SSM SecureString 응답의 설정 전체와 버전을 비공개로 고정한다."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import APP_KEYS, ReleaseError, checked_mapping, private_path

MAX_PARAMETER_BYTES = 8192
MAX_RESPONSE_BYTES = 65536
MAX_VERSION = 9223372036854775807
REGION = re.compile(r"[a-z]{2}(?:-[a-z]+)+-[0-9]\Z")
NAME = re.compile(r"/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\Z")
ERROR_CODES = frozenset(
    {
        "ssm_source_invalid",
        "ssm_version_invalid",
        "ssm_read_failed",
        "ssm_response_invalid",
        "ssm_settings_invalid",
    }
)


class SourceError(Exception):
    """원문 응답·명령·설정값 없이 고정된 오류 코드만 전달한다."""

    def __init__(self, code: str) -> None:
        super().__init__(code if code in ERROR_CODES else "ssm_read_failed")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError("nonstandard JSON constant")


def json_object(contents: bytes | str) -> dict[str, Any]:
    value = json.loads(
        contents, object_pairs_hook=unique_object, parse_constant=reject_constant
    )
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


@dataclass(frozen=True)
class Snapshot:
    app_env: dict[str, str] = field(repr=False)
    revision: str
    metadata: dict[str, str | int]


@dataclass(frozen=True)
class Source:
    region: str
    parameter_name: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.region, str)
            or not REGION.fullmatch(self.region)
            or not isinstance(self.parameter_name, str)
            or not NAME.fullmatch(self.parameter_name)
            or len(self.parameter_name) > 1011
            or self.parameter_name.count("/") > 15
            or self.parameter_name[1:].lower().startswith(("aws", "ssm"))
        ):
            raise SourceError("ssm_source_invalid")

    @classmethod
    def read(cls, path: Path) -> Source:
        """root 소유 설정의 경로·리전만 허용하며 요청으로 대상을 바꾸지 않는다."""
        try:
            private_path(path)
            if not path.is_absolute() or path != path.resolve():
                raise ValueError("source path must be absolute and direct")
            contents = path.read_bytes()
            if len(contents) > 4096:
                raise ValueError("source configuration too large")
            value = json_object(contents)
            if set(value) != {"region", "parameter_name"}:
                raise ValueError("source fields differ")
            return cls(**value)
        except (OSError, ValueError, TypeError, ReleaseError, SourceError):
            raise SourceError("ssm_source_invalid") from None

    def fetch(self, version: int, runner: Callable[..., bytes]) -> Snapshot:
        """고정 버전만 읽으며 누락·권한 실패를 최신값으로 대체하지 않는다."""
        if type(version) is not int or not 1 <= version <= MAX_VERSION:
            raise SourceError("ssm_version_invalid")
        return self._fetch(version, runner)

    def fetch_latest(self, runner: Callable[..., bytes]) -> Snapshot:
        """이름으로 한 번 조회한 응답의 값과 버전을 함께 고정한다."""
        return self._fetch(None, runner)

    def _fetch(self, version: int | None, runner: Callable[..., bytes]) -> Snapshot:
        try:
            output = runner(
                [
                    "aws",
                    "ssm",
                    "get-parameter",
                    "--name",
                    self.parameter_name
                    if version is None
                    else f"{self.parameter_name}:{version}",
                    "--with-decryption",
                    "--region",
                    self.region,
                    "--output",
                    "json",
                    "--no-cli-pager",
                    "--cli-connect-timeout",
                    "5",
                    "--cli-read-timeout",
                    "15",
                ],
                timeout=60,
            )
        except Exception:  # noqa: BLE001 -- AWS 오류 원문에 비밀값을 남기지 않는다.
            raise SourceError("ssm_read_failed") from None
        try:
            if not isinstance(output, bytes) or len(output) > MAX_RESPONSE_BYTES:
                raise ValueError("SSM response too large or not bytes")
            result = json_object(output)
            parameter = result["Parameter"]
            selected_version = (
                parameter.get("Version") if isinstance(parameter, dict) else None
            )
            if (
                not isinstance(parameter, dict)
                or parameter.get("Name") != self.parameter_name
                or type(selected_version) is not int
                or not 1 <= selected_version <= MAX_VERSION
                or (version is not None and selected_version != version)
                or parameter.get("Type") != "SecureString"
                or parameter.get("DataType") != "text"
                or parameter.get("Selector")
                != (f":{version}" if version is not None else None)
                or not isinstance(parameter.get("ARN"), str)
                or not re.fullmatch(
                    rf"arn:aws(?:-cn|-us-gov)?:ssm:{re.escape(self.region)}:"
                    rf"[0-9]{{12}}:parameter{re.escape(self.parameter_name)}",
                    parameter["ARN"],
                )
            ):
                raise ValueError("SSM identity does not match")
            version = selected_version
            contents = parameter["Value"]
            if (
                not isinstance(contents, str)
                or not contents
                or len(contents.encode("utf-8")) > MAX_PARAMETER_BYTES
            ):
                raise ValueError("SSM value invalid")
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise SourceError("ssm_response_invalid") from None
        try:
            environment = checked_mapping(json_object(contents), APP_KEYS)
            if not environment:
                raise ValueError("empty settings")
            # 정렬·공백 차이는 같은 설정으로 취급하지만 삭제 후 같은 이름과
            # 버전으로 재생성된 다른 값은 다른 배포 식별자를 갖는다.
            canonical = json.dumps(
                [self.region, self.parameter_name, version, environment],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, ReleaseError):
            raise SourceError("ssm_settings_invalid") from None
        digest = hashlib.sha256(canonical).hexdigest()
        return Snapshot(
            dict(environment),
            f"ssm-{version}-{digest[:40]}",
            {
                "region": self.region,
                "parameter_name": self.parameter_name,
                "parameter_version": version,
                "sha256": digest,
            },
        )
