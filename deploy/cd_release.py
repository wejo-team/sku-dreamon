"""검증한 소스·이미지만 기존 단일 호스트 배포 엔진에 전달한다."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MARKER = ".cd-source.json"
MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 30000
SLOTS = ("app_blue", "app_green")


class CDError(Exception):
    """호출자에게 공개할 고정 코드만 전달한다."""


def run(arguments: list[str], *, data: bytes | None = None, timeout: int = 60) -> bytes:
    """명령·stdout·stderr·임시 인증값을 로그나 예외에 포함하지 않는다."""
    try:
        return subprocess.run(
            arguments,
            input=data,
            stdin=subprocess.DEVNULL if data is None else None,
            capture_output=True,
            timeout=timeout,
            check=True,
            env={
                **{
                    key: os.environ[key]
                    for key in ("PATH", "HOME", "LANG")
                    if key in os.environ
                },
                "AWS_PAGER": "",
                "AWS_MAX_ATTEMPTS": "3",
                "AWS_RETRY_MODE": "standard",
            },
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise CDError("host_operation_failed") from None


def trusted(path: Path, *, directory: bool = False, private: bool = False) -> None:
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & (0o077 if private else 0o022)
        or path != path.resolve()
    ):
        raise CDError("unsafe_local_path")


def read_json(path: Path, *, private: bool = True) -> dict[str, Any]:
    trusted(path, private=private)
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CDError("invalid_metadata")
    return value


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class Config:
    region: str
    artifact_bucket: str
    ecr_repository_url: str
    runtime_config: Path
    releases_dir: Path
    current_link: Path

    @classmethod
    def read(cls, path: Path) -> Config:
        value = read_json(path)
        if set(value) != set(cls.__dataclass_fields__):
            raise CDError("invalid_config")
        if any(
            not isinstance(item, str) or any(c in item for c in "\r\n\0")
            for item in value.values()
        ):
            raise CDError("invalid_config")
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-[0-9]", value["region"]):
            raise CDError("invalid_config")
        if not re.fullmatch(
            r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", value["artifact_bucket"]
        ):
            raise CDError("invalid_config")
        repository = value["ecr_repository_url"]
        if not re.fullmatch(
            rf"[0-9]{{12}}\.dkr\.ecr\.{re.escape(value['region'])}\.amazonaws\.com/[a-z0-9]+(?:[._/-][a-z0-9]+)*",
            repository,
        ):
            raise CDError("invalid_config")
        for key in ("runtime_config", "releases_dir", "current_link"):
            value[key] = Path(value[key])
            if not value[key].is_absolute():
                raise CDError("invalid_config")
        result = cls(**value)
        trusted(result.runtime_config, private=True)
        trusted(result.releases_dir, directory=True)
        trusted(result.current_link.parent, directory=True)
        if result.current_link.parent != result.releases_dir.parent:
            raise CDError("invalid_config")
        return result


def tree_hash(root: Path) -> str:
    """캐시가 검증 후 수정되거나 링크로 바뀌면 재사용하지 않는다."""
    digest = hashlib.sha256()
    count = 0
    size = 0
    for path in sorted(root.rglob("*")):
        if path == root / MARKER:
            continue
        info = path.lstat()
        is_directory = stat.S_ISDIR(info.st_mode)
        trusted(path, directory=is_directory)
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts:
            # 기존 백업·인증서 CLI가 만든 캐시는 소스가 아니다. 엔진 로더는
            # 아래에서 .py 원문만 실행하며 캐시의 소유권·종류도 확인한다.
            if is_directory and path.name == "__pycache__":
                continue
            match = re.fullmatch(
                r"([a-zA-Z_][a-zA-Z0-9_]*)\.cpython-[0-9]+(?:\.opt-[0-9]+)?\.pyc",
                path.name,
            )
            if is_directory or path.parent.name != "__pycache__" or match is None:
                raise CDError("unexpected_python_cache")
            trusted(path.parent.parent / (match[1] + ".py"))
            continue
        count += 1
        size += 0 if is_directory else info.st_size
        if count > MAX_FILES or size > MAX_BYTES:
            raise CDError("source_limit_exceeded")
        digest.update(
            json.dumps(
                [
                    path.relative_to(root).as_posix(),
                    stat.S_IMODE(info.st_mode),
                    is_directory,
                ]
            ).encode()
        )
        if not is_directory:
            digest.update(file_hash(path).encode())
    return digest.hexdigest()


def extract(archive: Path, destination: Path) -> None:
    """새 디렉터리에 일반 파일·디렉터리만 푼다. 링크는 모두 거부한다."""
    seen: set[str] = set()
    total = 0
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            name = member.name.rstrip("/") if member.isdir() else member.name
            relative = PurePosixPath(name)
            if (
                not name
                or relative.is_absolute()
                or any(part in ("", ".", "..") for part in name.split("/"))
                or "\\" in name
                or any(ord(char) < 32 for char in name)
                or relative.parts[0] == MARKER
                or "__pycache__" in relative.parts
                or relative.suffix == ".pyc"
                or name in seen
                or not (member.isfile() or member.isdir())
            ):
                raise CDError("unsafe_source_archive")
            seen.add(name)
            total += member.size
            if len(seen) > MAX_FILES or total > MAX_BYTES or member.size < 0:
                raise CDError("source_limit_exceeded")
            path = destination.joinpath(*relative.parts)
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            if member.isdir():
                path.mkdir(mode=0o755, exist_ok=True)
                continue
            mode = 0o755 if member.mode & 0o111 else 0o644
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode
            )
            with os.fdopen(fd, "wb") as output, source.extractfile(member) as content:
                remaining = member.size
                while remaining:
                    chunk = content.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise CDError("invalid_source_archive")
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
    for name in (
        "deploy/release.py",
        "deploy/config.py",
        "deploy/compose.production.yaml",
    ):
        trusted(destination / name)


@contextmanager
def engine(config: Config, checkout: Path) -> Iterator[Any]:
    """현재 실행 동안만 해당 릴리스의 엔진·설정 모듈을 사용한다."""
    trusted(checkout, directory=True)
    saved = {
        name: sys.modules.get(name) for name in ("config", "release", "ssm_config")
    }
    bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(checkout / "deploy"))
    try:
        for name in ("config", "release", "ssm_config"):
            path = checkout / "deploy" / f"{name}.py"
            if name == "ssm_config" and not path.exists():
                sys.modules.pop(name, None)
                continue
            trusted(path)
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise CDError("engine_unavailable")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            # dont_write_bytecode만으로는 기존 .pyc 읽기를 막지 못한다.
            exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)  # noqa: S102 -- 검증한 엔진 .py만 캐시 없이 로드한다.
        runtime = sys.modules["config"].Runtime.read(config.runtime_config, checkout)
        release = sys.modules["release"].Release(runtime, checkout)
        release.configuration_app_keys = getattr(
            sys.modules["config"], "APP_KEYS", frozenset()
        )
        source = sys.modules.get("ssm_config")
        release.configuration_source = (
            source.Source.read if source is not None else None
        )
        yield release
    finally:
        sys.path.pop(0)
        sys.dont_write_bytecode = bytecode
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class CDRelease:
    def __init__(
        self,
        config: Config,
        *,
        runner=run,
        engine_factory=engine,
        source_path=Path("/etc/sku-dreamon/ssm-config.json"),
        source_factory=None,
    ) -> None:
        self.config = config
        self.runner = runner
        self.engine_factory = engine_factory
        runtime = read_json(config.runtime_config)
        self.root = Path(runtime["runtime_dir"])
        trusted(self.root, directory=True, private=True)
        trusted(self.root / "state", directory=True, private=True)
        from code_config import CodeConfiguration

        self.configuration = CodeConfiguration(self, source_path, source_factory)

    @contextmanager
    def lock(self) -> Iterator[None]:
        path = self.root / "state" / "cd.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            trusted(path, private=True)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CDError("cd_busy") from None
            yield
        finally:
            os.close(fd)

    def checkout(self, sha: str) -> Path:
        if not SHA.fullmatch(sha):
            raise CDError("invalid_sha")
        path = self.config.releases_dir / sha
        trusted(path, directory=True)
        return path

    def current_sha(self) -> str:
        link = self.config.current_link
        info = link.lstat()
        if not stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid():
            raise CDError("invalid_current_link")
        target = link.resolve(strict=True)
        if target.parent != self.config.releases_dir or not SHA.fullmatch(target.name):
            raise CDError("invalid_current_link")
        self.checkout(target.name)
        return target.name

    @staticmethod
    def summary(release) -> dict[str, Any]:
        state = release.state

        def record(slot):
            if slot is None:
                return {}
            if slot not in SLOTS or slot not in state["slots"]:
                raise CDError("invalid_journal")
            value = state["slots"][slot]
            if not SHA.fullmatch(value["sha"]):
                raise CDError("invalid_journal")
            return value

        active = record(state.get("active"))
        previous = record(state.get("previous"))
        if state.get("phase") not in (
            "empty",
            "bootstrap",
            "bootstrap_pending",
            "pending",
            "stable",
            "failed",
        ):
            raise CDError("invalid_journal")
        image = active.get("image")
        if image is not None and not re.fullmatch(
            r"(?:[a-zA-Z0-9][a-zA-Z0-9./_:-]*@)?sha256:[0-9a-f]{64}", image
        ):
            raise CDError("invalid_journal")
        return {
            "phase": state["phase"],
            "active_sha": active.get("sha"),
            "previous_sha": previous.get("sha"),
            "active_image": image,
        }

    def stable(self, release) -> dict[str, Any]:
        pending = self.root / "state" / "config-pending.json"
        if pending.exists() or pending.is_symlink():
            raise CDError("configuration_recovery_required")
        if (
            self.configuration.pending.exists()
            or self.configuration.pending.is_symlink()
        ):
            raise CDError("code_configuration_recovery_required")
        result = self.summary(release)
        if (
            result["phase"] != "stable"
            or release.state.get("transaction")
            or release.state.get("certificate")
            or result["active_sha"] is None
        ):
            raise CDError("release_unstable")
        release.verify_host()
        return result

    def guard(self, release, expected: str, sha: str, image: str) -> bool:
        status = self.stable(release)
        active_record = release.state["slots"][release.state["active"]]
        environment = "".join(
            f"{key}={value}\n" for key, value in sorted(release.runtime.app_env.items())
        )
        if (
            hashlib.sha256(environment.encode()).hexdigest()
            != active_record["env_hash"]
            or release.runtime.config_revision != active_record["config_revision"]
        ):
            raise CDError("configuration_requires_dedicated_release")
        active = status["active_sha"]
        duplicate = (
            active == sha
            and status["active_image"] == image
            and (expected == sha or status["previous_sha"] == expected)
        )
        if not duplicate and active != expected:
            raise CDError("current_release_changed")
        if active == sha and not duplicate:
            raise CDError("same_sha_image_changed")
        if self.current_sha() not in ({active, expected} if duplicate else {active}):
            raise CDError("current_link_drift")
        return duplicate

    def status(self) -> dict[str, Any]:
        with self.lock():
            pending = self.configuration.pending
            snapshot = None
            if pending.exists() or pending.is_symlink():
                journal, _, _ = self.configuration.journal()
                side = (
                    "old" if self.current_sha() == journal["before"]["sha"] else "new"
                )
                snapshot = journal[f"{side}_snapshot"]
            with self.configuration.code_engine(
                self.checkout(self.current_sha()), snapshot
            ) as release:
                return {
                    **self.summary(release),
                    "code_config_phase": "pending" if snapshot is not None else "idle",
                }

    def source(self, sha: str, source_hash: str, image_digest: str) -> Path:
        target = self.config.releases_dir / sha
        identity = {
            "sha": sha,
            "source_sha256": source_hash,
            "image_digest": image_digest,
        }
        if target.exists() or target.is_symlink():
            self.checkout(sha)
            marker = read_json(target / MARKER)
            if marker != {**identity, "tree_sha256": tree_hash(target)}:
                raise CDError("cached_source_mismatch")
            return target
        with tempfile.TemporaryDirectory(
            prefix=".cd-source-", dir=self.config.releases_dir
        ) as temporary:
            temporary = Path(temporary)
            archive = temporary / "source.tar.gz"
            self.runner(
                [
                    "aws",
                    "s3",
                    "cp",
                    f"s3://{self.config.artifact_bucket}/artifacts/cd/{sha}/source.tar.gz",
                    str(archive),
                    "--region",
                    self.config.region,
                    "--only-show-errors",
                ],
                timeout=300,
            )
            trusted(archive)
            if archive.stat().st_size > MAX_BYTES or file_hash(archive) != source_hash:
                raise CDError("source_hash_mismatch")
            checkout = temporary / "checkout"
            checkout.mkdir(mode=0o755)
            extract(archive, checkout)
            marker = {**identity, "tree_sha256": tree_hash(checkout)}
            descriptor = os.open(
                checkout / MARKER, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            with os.fdopen(descriptor, "w") as output:
                output.write(json.dumps(marker, sort_keys=True) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.rename(checkout, target)
            self.sync_directory(self.config.releases_dir)
        return target

    def pull(self, sha: str, image: str) -> None:
        with tempfile.TemporaryDirectory(
            prefix="cd-docker-", dir=self.root / "state"
        ) as temporary:
            password = self.runner(
                ["aws", "ecr", "get-login-password", "--region", self.config.region]
            )
            if not password.strip():
                raise CDError("ecr_login_failed")
            docker = [
                "docker",
                "--host",
                "unix:///var/run/docker.sock",
                "--config",
                temporary,
            ]
            self.runner(
                [
                    *docker,
                    "login",
                    "--username",
                    "AWS",
                    "--password-stdin",
                    self.config.ecr_repository_url.split("/", 1)[0],
                ],
                data=password,
            )
            self.runner([*docker, "pull", image], timeout=600)
            result = json.loads(self.runner([*docker, "image", "inspect", image]))
            if (
                len(result) != 1
                or (result[0].get("Config", {}).get("Labels") or {}).get(
                    "org.opencontainers.image.revision"
                )
                != sha
                or image not in (result[0].get("RepoDigests") or [])
            ):
                raise CDError("image_identity_mismatch")

    def backup(self, expected: str) -> None:
        marker = self.root / "state" / "backup-last-success.json"
        before = read_json(marker).get("backup_id") if marker.exists() else None
        self.runner(["systemctl", "start", "sku-dreamon-backup.service"], timeout=7200)
        after = read_json(marker)
        if (
            after.get("status") != "complete"
            or not after.get("backup_id")
            or after["backup_id"] == before
            or after.get("release_sha") != expected
            or len(after.get("objects", [])) != 2
        ):
            raise CDError("fresh_backup_required")

    @staticmethod
    def sync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def publish(self, sha: str, *, allowed: set[str]) -> None:
        if self.current_sha() not in allowed:
            raise CDError("current_link_drift")
        target = self.checkout(sha)
        temporary = self.config.current_link.with_name(f".current-cd-{os.getpid()}")
        try:
            os.symlink(target, temporary)
            os.replace(temporary, self.config.current_link)
            self.sync_directory(self.config.current_link.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def restore_after_failure(self, release, expected: str, target: str) -> None:
        """이번 전환만 엔진의 복구·롤백으로 되돌린다. journal을 수정하지 않는다."""
        try:
            release.load()
            transaction = release.state.get("transaction")
            if transaction:
                slots = release.state["slots"]
                if (
                    slots[transaction["target"]]["sha"] != target
                    or slots[transaction["old"]]["sha"] != expected
                ):
                    raise CDError("recovery_required")
                release.recover()
            status = self.stable(release)
            if status["active_sha"] == target and status["previous_sha"] == expected:
                release.rollback()
                status = self.stable(release)
            if status["active_sha"] != expected:
                raise CDError("recovery_required")
            release.reconcile()
            self.publish(expected, allowed={expected, target})
        except Exception:  # noqa: BLE001 -- 복구가 불확실하면 오류 원문 없이 중단한다.
            raise CDError("recovery_required") from None

    def change(
        self,
        action: str,
        sha: str,
        expected: str,
        source_hash: str | None = None,
        image_digest: str | None = None,
    ) -> dict[str, Any]:
        if (
            action not in ("deploy", "rollback")
            or not SHA.fullmatch(sha)
            or not SHA.fullmatch(expected)
        ):
            raise CDError("invalid_request")
        if action == "rollback" and sha == expected:
            raise CDError("configuration_requires_dedicated_release")
        if action == "deploy" and (
            source_hash is None
            or not DIGEST.fullmatch(source_hash)
            or image_digest is None
            or not DIGEST.fullmatch(image_digest)
        ):
            raise CDError("invalid_request")
        with self.lock():
            current = self.current_sha()
            with (
                self.engine_factory(self.config, self.checkout(current)) as release,
                release.lock(),
            ):
                status = self.stable(release)
                if action == "rollback":
                    if (
                        status["active_sha"] != expected
                        or status["previous_sha"] != sha
                        or current != expected
                    ):
                        raise CDError("rollback_target_changed")
                    image = release.state["slots"][release.state["previous"]]["image"]
                    prefix = self.config.ecr_repository_url + "@sha256:"
                    if not image.startswith(prefix) or not DIGEST.fullmatch(
                        image.removeprefix(prefix)
                    ):
                        raise CDError("rollback_image_mismatch")
                    if image_digest is not None and image != prefix + image_digest:
                        raise CDError("rollback_image_mismatch")
                    duplicate = False
                else:
                    image = self.config.ecr_repository_url + "@sha256:" + image_digest
                    duplicate = self.guard(release, expected, sha, image)
            checkout = (
                self.source(sha, source_hash, image_digest)
                if action == "deploy"
                else self.checkout(sha)
            )
            if action == "rollback" and source_hash is not None:
                marker = read_json(checkout / MARKER)
                if marker.get("source_sha256") != source_hash or marker.get(
                    "tree_sha256"
                ) != tree_hash(checkout):
                    raise CDError("cached_source_mismatch")
            self.pull(sha, image)
            operation = self.configuration
            if duplicate:
                with (
                    self.engine_factory(self.config, checkout) as release,
                    release.lock(),
                ):
                    self.guard(release, expected, sha, image)
                    release.reconcile()
                    self.publish(sha, allowed={expected, sha})
                    result = self.stable(release)
                    return {
                        "deployed_sha": result["active_sha"],
                        "previous_sha": result["previous_sha"],
                    }

            # 새 설정은 대상 코드의 parser로 읽는다. rollback은 현재 코드에서
            # 이전 슬롯의 설정을 먼저 확보해 구 parser에 새 키를 전달하지 않는다.
            selection_checkout = (
                checkout if action == "deploy" else self.checkout(current)
            )
            with (
                self.engine_factory(self.config, selection_checkout) as release,
                release.lock(),
            ):
                if action == "deploy":
                    self.guard(release, expected, sha, image)
                else:
                    self.stable(release)
                old, new, before, configured = operation.select(release, action)
                if action == "deploy":
                    candidate = release.runtime.__class__.parse(new, checkout)
                    if candidate.host_identity != release.runtime.host_identity:
                        raise CDError("host_configuration_changed")
            after = {**configured, "sha": sha, "image": image}
            self.backup(expected)
            # 백업은 기존 안정 쌍을 읽으며 snapshot과 pending은 성공 후에만 만든다.
            try:
                with (
                    self.engine_factory(self.config, self.checkout(current)) as release,
                    release.lock(),
                ):
                    status = self.stable(release)
                    if (
                        status["active_sha"] != expected
                        or operation.active(release) is None
                        or any(
                            operation.active(release).get(key) != value
                            for key, value in before.items()
                        )
                        or read_json(self.config.runtime_config) != old
                        or self.current_sha() != expected
                    ):
                        raise CDError("current_release_changed")
                    journal = operation.start(action, old, new, before, after)
                # snapshot을 engine 입력으로만 사용하고 실제 runtime은 전환 후 게시한다.
                with operation.code_engine(
                    checkout, journal["new_snapshot"]
                ) as release:
                    if release.runtime.host_identity != release.state["host_identity"]:
                        raise CDError("host_configuration_changed")
                    if any(
                        operation.active(release).get(key) != value
                        for key, value in before.items()
                    ):
                        raise CDError("current_release_changed")
                    if action == "deploy":
                        release.deploy(image, sha, migrate=True)
                    else:
                        previous = release.state["slots"][release.state["previous"]]
                        if any(
                            previous.get(key) != value for key, value in after.items()
                        ):
                            raise CDError("rollback_target_changed")
                        release.rollback()
                    operation.finish(release, old, new, after)
            except Exception:
                if operation.pending.exists() or operation.pending.is_symlink():
                    try:
                        operation.undo()
                    except Exception:  # noqa: BLE001 -- 복구 오류 원문 대신 고정 코드만 공개한다.
                        raise CDError("code_configuration_recovery_required") from None
                    raise CDError("release_failed_restored") from None
                raise
            return {"deployed_sha": sha, "previous_sha": expected}


def main() -> int:
    parser = argparse.ArgumentParser(description="Guarded production CD runner")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--action", choices=("status", "deploy", "rollback", "recover"), required=True
    )
    parser.add_argument("--sha")
    parser.add_argument("--source-sha256")
    parser.add_argument("--image-digest")
    parser.add_argument("--expected-current")
    arguments = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise CDError("root_required")
        cd = CDRelease(Config.read(arguments.config))
        if arguments.action == "status":
            result = cd.status()
        elif arguments.action == "recover":
            result = cd.configuration.recover()
        else:
            if arguments.sha is None or arguments.expected_current is None:
                raise CDError("invalid_request")
            result = cd.change(
                arguments.action,
                arguments.sha,
                arguments.expected_current,
                arguments.source_sha256,
                arguments.image_digest,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 -- 비밀값이 포함될 수 있는 최종 프로세스 경계.
        # 런타임 JSON·하위 도구·배포 엔진의 예외 원문을 노출하지 않는다.
        code = (
            str(error)
            if type(error) is CDError and re.fullmatch(r"[a-z_]{3,64}", str(error))
            else "cd_failed"
        )
        print(json.dumps({"error": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.modules["cd_release"] = sys.modules[__name__]
    raise SystemExit(main())
