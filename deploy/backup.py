"""안정된 릴리스의 DB·복구 설정을 암호화 S3에 보관하며 원본을 삭제하지 않는다."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from config import ReleaseError, Runtime, atomic_write

REQUIRED_PRIVATE = frozenset(
    {
        "db-ca.crt",
        "db-ca.key",
        "postgres.crt",
        "postgres.key",
        "postgres-bootstrap-password",
        "app-password",
        "migration-password",
        "password-blocklist.txt",
        "compose.env",
    }
)
OPTIONAL_PRIVATE = frozenset(
    {
        "password-blocklist-source.json",
        "password-blocklist-LICENSE.txt",
    }
)
ENV_FILE = re.compile(r"(?:app|migrate|postgres|unassigned)-[a-f0-9]{64}\.env")
OPENAI_KEY_SENTINEL = "__REHYDRATE_OPENAI_API_KEY_FROM_SSM__"
ERROR_CODES = frozenset(
    {
        "not_root",
        "options_invalid",
        "runtime_invalid",
        "command_failed",
        "lock_unavailable",
        "release_not_stable",
        "target_invalid",
        "mount_invalid",
        "dump_failed",
        "archive_invalid",
        "upload_failed",
        "verification_failed",
        "operation_failed",
        "unsafe_path",
    }
)


class BackupError(Exception):
    """실패 원문 대신 고정 코드만 로그·알림에 전달한다."""

    def __init__(self, code: str) -> None:
        super().__init__(code if code in ERROR_CODES else "operation_failed")


def now() -> str:
    return datetime.now(UTC).isoformat()


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def command(
    arguments: list[str], *, output: BinaryIO | None = None, timeout: int = 60
) -> bytes:
    """명령·stderr·환경의 원문은 출력하지 않고 instance role로 AWS를 호출한다."""
    environment = {
        key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ
    }
    environment.update(AWS_PAGER="", AWS_MAX_ATTEMPTS="3", AWS_RETRY_MODE="standard")
    try:
        result = subprocess.run(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=output if output is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=True,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        raise BackupError("command_failed") from None
    return result.stdout or b""


@dataclass(frozen=True)
class Options:
    bucket: str
    region: str
    topic: str = ""
    kms_key: str = ""

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", self.bucket)
            or ".." in self.bucket
            or not re.fullmatch(r"[a-z]{2}-[a-z0-9-]+-[0-9]+", self.region)
            or (
                self.topic
                and not re.fullmatch(
                    rf"arn:aws:sns:{re.escape(self.region)}:[0-9]{{12}}:[A-Za-z0-9_-]+",
                    self.topic,
                )
            )
            or (
                self.kms_key
                and not re.fullmatch(r"[A-Za-z0-9:/_-]{1,2048}", self.kms_key)
            )
        ):
            raise BackupError("options_invalid")

    @classmethod
    def from_environment(cls) -> Options:
        return cls(
            os.environ.get("BACKUP_BUCKET", ""),
            os.environ.get("BACKUP_REGION", ""),
            os.environ.get("BACKUP_SNS_TOPIC_ARN", ""),
            os.environ.get("BACKUP_KMS_KEY_ID", ""),
        )


def checked_stat(path: Path, *, private: bool = False) -> os.stat_result:
    info = path.lstat()
    # main이 root 실행을 강제한다. 링크는 아래 archive 경계에서 별도 검사한다.
    if info.st_uid != os.geteuid() or (
        not stat.S_ISLNK(info.st_mode) and info.st_mode & (0o077 if private else 0o022)
    ):
        raise BackupError("unsafe_path")
    return info


class Backup:
    def __init__(
        self,
        runtime: Runtime,
        config: Path,
        checkout: Path,
        options: Options,
        runner: Callable = command,
    ) -> None:
        self.runtime = runtime
        self.config = config
        self.checkout = checkout
        self.options = options
        self.runner = runner
        self.openai_key_redacted = False

    def docker(self, *arguments: str) -> bytes:
        return self.runner(
            ["docker", "--host", "unix:///var/run/docker.sock", *arguments]
        )

    @contextmanager
    def release_lock(self) -> Iterator[dict]:
        directory = self.runtime.root / "state"
        if not stat.S_ISDIR(checked_stat(directory, private=True).st_mode):
            raise BackupError("unsafe_path")
        descriptor = os.open(
            directory / "release.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
            ):
                raise BackupError("unsafe_path")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise BackupError("lock_unavailable") from None
            pending = directory / "config-pending.json"
            if pending.exists() or pending.is_symlink():
                raise BackupError("release_not_stable")
            journal = directory / "release.json"
            if not stat.S_ISREG(checked_stat(journal, private=True).st_mode):
                raise BackupError("unsafe_path")
            state = json.loads(journal.read_text())
            if (
                state.get("version") != 1
                or state.get("phase") != "stable"
                or state.get("transaction")
                or state.get("certificate")
                or state.get("host_identity") != self.runtime.host_identity
                or state.get("active") not in ("app_blue", "app_green")
            ):
                raise BackupError("release_not_stable")
            yield state
        finally:
            os.close(descriptor)

    def postgres(self, state: dict) -> str:
        ids = (
            self.docker(
                "ps",
                "--filter",
                "status=running",
                "--filter",
                f"label=com.docker.compose.project={self.runtime.project}",
                "--filter",
                "label=com.docker.compose.service=postgres",
                "--format",
                "{{.ID}}",
            )
            .decode()
            .split()
        )
        if len(ids) != 1:
            raise BackupError("target_invalid")
        records = json.loads(self.docker("inspect", ids[0]))
        if not isinstance(records, list) or len(records) != 1:
            raise BackupError("target_invalid")
        record = records[0]
        labels = record.get("Config", {}).get("Labels", {})
        if (
            not record.get("State", {}).get("Running")
            or record.get("Id") != state.get("postgres_id")
            or not re.fullmatch(r"[a-f0-9]{64}", record.get("Id", ""))
            or labels.get("com.docker.compose.project") != self.runtime.project
            or labels.get("com.docker.compose.service") != "postgres"
            or "PGDATA=/var/lib/postgresql/data"
            not in record.get("Config", {}).get("Env", [])
        ):
            raise BackupError("target_invalid")
        mounts = [
            item
            for item in record.get("Mounts", [])
            if item.get("Destination") == "/var/lib/postgresql/data"
        ]
        if (
            len(mounts) != 1
            or mounts[0].get("Type") != "bind"
            or mounts[0].get("RW") is not True
            or mounts[0].get("Source") != str(self.runtime.data_dir)
        ):
            raise BackupError("mount_invalid")
        try:
            self.runner(
                [
                    "sh",
                    str(self.checkout / "deploy/postgres/check-mount.sh"),
                    str(self.runtime.mount_path),
                    self.runtime.filesystem_uuid,
                    str(self.runtime.data_dir),
                ],
                timeout=15,
            )
        except BackupError:
            raise BackupError("mount_invalid") from None
        return record["Id"]

    def archive(self, destination: Path) -> None:
        root = self.runtime.root
        private = root / "private"
        if not stat.S_ISDIR(checked_stat(private, private=True).st_mode):
            raise BackupError("unsafe_path")
        selected = [self.config]
        for name in sorted(REQUIRED_PRIVATE):
            path = private / name
            if not stat.S_ISREG(checked_stat(path).st_mode):
                raise BackupError("archive_invalid")
            selected.append(path)
        for path in sorted(private.iterdir()):
            if path.name in OPTIONAL_PRIVATE or ENV_FILE.fullmatch(path.name):
                selected.append(path)
        selected.append(root / "state/release.json")
        trees = [root / "nginx", root / "state/certbot", root / "acme/letsencrypt"]
        if any(
            self.runtime.data_dir.is_relative_to(tree) for tree in trees + [private]
        ):
            raise BackupError("archive_invalid")
        with tarfile.open(destination, "w:gz", dereference=False) as archive:
            for path in selected:
                self.add_archive_entry(archive, path)
            for tree in trees:
                if not stat.S_ISDIR(checked_stat(tree).st_mode):
                    raise BackupError("archive_invalid")
                self.add_archive_entry(archive, tree)

    def add_archive_entry(self, archive: tarfile.TarFile, path: Path) -> None:
        info = checked_stat(path)
        if path == self.config:
            name = "configuration/runtime.json"
            if not stat.S_ISREG(checked_stat(path, private=True).st_mode):
                raise BackupError("archive_invalid")
        else:
            name = "runtime/" + str(path.relative_to(self.runtime.root))
        if path.name.endswith(".lock"):
            return
        if stat.S_ISLNK(info.st_mode):
            link = os.readlink(path)
            acme = self.runtime.root / "acme/letsencrypt"
            if (
                Path(link).is_absolute()
                or not path.is_relative_to(acme)
                or not path.resolve(strict=True).is_relative_to(acme)
            ):
                raise BackupError("archive_invalid")
            archive.add(path, arcname=name, recursive=False)
        elif stat.S_ISDIR(info.st_mode):
            archive.add(path, arcname=name, recursive=False)
            for child in sorted(path.iterdir()):
                self.add_archive_entry(archive, child)
        elif stat.S_ISREG(info.st_mode):
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as source:
                before = os.fstat(source.fileno())
                if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino):
                    raise BackupError("archive_invalid")
                member = archive.gettarinfo(fileobj=source, arcname=name)
                if path == self.config or path.suffix == ".env":
                    contents = self.redact_openai_key(path, source.read())
                    member.size = len(contents)
                    archive.addfile(member, io.BytesIO(contents))
                else:
                    archive.addfile(member, source)
                after = os.fstat(source.fileno())
                if (before.st_mtime_ns, before.st_size) != (
                    after.st_mtime_ns,
                    after.st_size,
                ):
                    raise BackupError("archive_invalid")
        else:
            raise BackupError("archive_invalid")

    def redact_openai_key(self, path: Path, contents: bytes) -> bytes:
        """모델 키는 SSM에서 복구하도록 자리만 남기며 원본 파일은 바꾸지 않는다."""
        if path == self.config:
            value = json.loads(contents)
            environment = value["app_env"]
            if "OPENAI_API_KEY" in environment:
                environment["OPENAI_API_KEY"] = OPENAI_KEY_SENTINEL
                self.openai_key_redacted = True
            return (
                json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            ).encode()
        lines = contents.split(b"\n")
        for index, line in enumerate(lines):
            if line.startswith(b"OPENAI_API_KEY="):
                lines[index] = b"OPENAI_API_KEY=" + OPENAI_KEY_SENTINEL.encode()
                self.openai_key_redacted = True
        return b"\n".join(lines)

    def upload(self, path: Path, key: str) -> dict:
        sha = digest(path)
        arguments = [
            "aws",
            "s3",
            "cp",
            str(path),
            f"s3://{self.options.bucket}/{key}",
            "--region",
            self.options.region,
            "--only-show-errors",
            "--sse",
            "aws:kms",
            "--metadata",
            f"sha256={sha}",
            "--checksum-algorithm",
            "SHA256",
        ]
        if self.options.kms_key:
            arguments += ["--sse-kms-key-id", self.options.kms_key]
        try:
            self.runner(arguments, timeout=1800)
        except BackupError:
            raise BackupError("upload_failed") from None
        actual = json.loads(
            self.runner(
                [
                    "aws",
                    "s3api",
                    "head-object",
                    "--bucket",
                    self.options.bucket,
                    "--key",
                    key,
                    "--region",
                    self.options.region,
                    "--output",
                    "json",
                ]
            )
        )
        if (
            actual.get("ContentLength") != path.stat().st_size
            or actual.get("Metadata", {}).get("sha256") != sha
            or actual.get("ServerSideEncryption") != "aws:kms"
        ):
            raise BackupError("verification_failed")
        return {"key": key, "sha256": sha, "bytes": path.stat().st_size}

    def run(self) -> dict:
        started_at = now()
        backup_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
        prefix = f"backups/{self.runtime.project}/{backup_id}"
        with self.release_lock() as state:
            container = self.postgres(state)
            staging = self.runtime.root / "backup-staging"
            staging.mkdir(mode=0o700, exist_ok=True)
            if not stat.S_ISDIR(checked_stat(staging, private=True).st_mode):
                raise BackupError("unsafe_path")
            with tempfile.TemporaryDirectory(
                dir=staging, prefix="capture-"
            ) as temporary:
                directory = Path(temporary)
                dump = directory / "database.dump"
                with dump.open("xb") as output:
                    dump.chmod(0o600)
                    try:
                        self.runner(
                            [
                                "docker",
                                "--host",
                                "unix:///var/run/docker.sock",
                                "exec",
                                "--user",
                                "postgres",
                                container,
                                "timeout",
                                "--signal=TERM",
                                "--kill-after=30s",
                                "1740s",
                                "pg_dump",
                                "--no-password",
                                "--username",
                                "postgres",
                                "--format=custom",
                                "--lock-wait-timeout=30s",
                                "--dbname",
                                self.runtime.postgres_env["POSTGRES_DB"],
                            ],
                            output=output,
                            timeout=1800,
                        )
                    except BackupError:
                        raise BackupError("dump_failed") from None
                with dump.open("rb") as source:
                    if source.read(5) != b"PGDMP" or dump.stat().st_size <= 5:
                        raise BackupError("dump_failed")
                recovery = directory / "runtime.tar.gz"
                self.archive(recovery)
                recovery.chmod(0o600)
                if self.postgres(state) != container:
                    raise BackupError("target_invalid")
                objects = [
                    self.upload(path, f"{prefix}/{path.name}")
                    for path in (dump, recovery)
                ]
                manifest = {
                    "format": "sku-dreamon-backup-v1",
                    "status": "complete",
                    "backup_id": backup_id,
                    "started_at": started_at,
                    "completed_at": now(),
                    "objects": objects,
                    "release_sha": state["slots"][state["active"]]["sha"],
                    "restored": False,
                    "openai_key_redacted": self.openai_key_redacted,
                }
                manifest_file = directory / "manifest.json"
                manifest_file.write_text(json.dumps(manifest, sort_keys=True) + "\n")
                self.upload(manifest_file, f"{prefix}/manifest.json")
                atomic_write(
                    self.runtime.root / "state/backup-last-success.json",
                    json.dumps(manifest, sort_keys=True) + "\n",
                )
                return manifest


def notify_failure(options: Options, code: str, runner: Callable = command) -> None:
    if not options.topic:
        return
    payload = json.dumps(
        {"event": "production_backup_failed", "code": code, "time": now()}
    )
    try:
        runner(
            [
                "aws",
                "sns",
                "publish",
                "--region",
                options.region,
                "--topic-arn",
                options.topic,
                "--message",
                payload,
            ]
        )
    except BackupError:
        print("backup_notification_failed", file=sys.stderr)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DB와 런타임의 암호화 S3 백업")
    parser.add_argument(
        "--config", type=Path, default=Path("/etc/sku-dreamon/runtime.json")
    )
    args = parser.parse_args(arguments)
    options = None
    try:
        if os.geteuid() != 0:
            raise BackupError("not_root")
        options = Options.from_environment()
        checkout = Path(__file__).resolve().parent.parent
        try:
            runtime = Runtime.read(args.config, checkout)
        except (ReleaseError, OSError, ValueError, TypeError):
            raise BackupError("runtime_invalid") from None
        result = Backup(runtime, args.config, checkout, options).run()
    # 최상위 운영 경계에서 예상 밖 오류도 비밀값·경로가 포함된
    # traceback으로 내보내지 않는다.
    except Exception as error:  # noqa: BLE001
        code = str(error) if isinstance(error, BackupError) else "operation_failed"
        print(json.dumps({"event": "backup_failed", "code": code}), file=sys.stderr)
        if options:
            notify_failure(options, code)
        return 1
    print(
        json.dumps(
            {
                "event": "backup_completed",
                "backup_id": result["backup_id"],
                "completed_at": result["completed_at"],
                "restored": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
