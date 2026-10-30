"""비공개 JSON에서 허용한 설정만 읽고 실행 없는 Compose 입력을 만든다."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


class ReleaseError(Exception):
    """비밀값이나 실행 명령을 포함하지 않는 운영 오류."""

    @property
    def code(self) -> str:
        # 고정 문구만 공개 코드로 바꾸며 임의 예외 문장은 출력하지 않는다.
        codes = (
            (
                "bounded host operation failed",
                "host_operation_failed",
            ),
            (
                "migration failed; explicit recovery is required",
                "migration_failed",
            ),
            (
                "migration is still running; recovery must observe its exit",
                "migration_running",
            ),
            (
                "migration is still running; no retry or new deployment is allowed",
                "migration_running",
            ),
            (
                "candidate did not become production ready",
                "candidate_not_ready",
            ),
            (
                "HTTPS traffic did not reach the expected release",
                "https_release_mismatch",
            ),
            (
                "image revision does not match the requested release",
                "image_identity_mismatch",
            ),
            (
                "image digest does not match the requested release",
                "image_identity_mismatch",
            ),
            (
                "app image or running identity differs from the journal",
                "image_identity_mismatch",
            ),
            (
                "actual app configuration differs from the release record",
                "config_identity_mismatch",
            ),
            (
                "drain deadline passed; graceful completion is unproven",
                "drain_deadline_exceeded",
            ),
            (
                "Nginx container or master changed during drain",
                "nginx_identity_mismatch",
            ),
            (
                "certificate job failed; active routing was preserved",
                "certificate_job_failed",
            ),
            (
                "host configuration changed outside an infrastructure procedure",
                "host_configuration_changed",
            ),
        )
        return dict(codes).get(str(self), "release_blocked")


IMAGE = re.compile(r"(?:[a-zA-Z0-9][a-zA-Z0-9./_:-]*@)?sha256:[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
REVISION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}\Z")
APP_KEYS = frozenset(
    "APP_ENV DATABASE_URL DATABASE_TLS_CA_FILE DATABASE_POOL_SIZE "
    "DATABASE_MAX_OVERFLOW DATABASE_POOL_TIMEOUT_SECONDS "
    "DATABASE_CONNECT_TIMEOUT_SECONDS DATABASE_COMMAND_TIMEOUT_SECONDS "
    "DATABASE_STATEMENT_TIMEOUT_SECONDS DATABASE_LOCK_TIMEOUT_SECONDS "
    "DATABASE_IDLE_TRANSACTION_TIMEOUT_SECONDS READINESS_TIMEOUT_SECONDS "
    "SHUTDOWN_TIMEOUT_SECONDS HTTP_ALLOWED_HOSTS HTTP_TRUSTED_PROXIES "
    "OPENAI_API_KEY AI_REQUIRED AI_MODEL AI_REASONING_EFFORT AI_TIMEOUT_SECONDS "
    "LANGSMITH_TRACING LANGSMITH_API_KEY LANGSMITH_PROJECT LANGSMITH_ENDPOINT "
    "LANGSMITH_WORKSPACE_ID "
    "AI_CLEANUP_TIMEOUT_SECONDS AI_RETENTION_SECONDS AI_MAX_OUTPUT_TOKENS "
    "AI_MAX_INPUT_TOKENS AI_MAX_TOOL_CALLS AI_MAX_SOURCES AI_REQUESTS_PER_HOUR "
    "AI_CONCURRENT_REQUESTS CSRF_SIGNING_KEY AUTH_ALLOWED_ORIGINS "
    "PASSWORD_BLOCKLIST_PATH PASSWORD_BLOCKLIST_VERSION AUTH_LOGIN_ACCOUNT_LIMIT "
    "AUTH_LOGIN_IP_LIMIT AUTH_SIGNUP_IP_LIMIT AUTH_AVAILABILITY_IP_LIMIT".split()
)
MIGRATION_KEYS = frozenset(
    key for key in APP_KEYS if key.startswith("DATABASE_") or key == "APP_ENV"
)
POSTGRES_KEYS = frozenset({"POSTGRES_USER", "POSTGRES_DB"})
COMPOSE_KEYS = frozenset(
    "NGINX_PROXY_IP APP_NETWORK_SUBNET DB_NETWORK_SUBNET NGINX_HTTP_PORT "
    "NGINX_HTTPS_PORT NGINX_BIND_IP".split()
)


def private_path(path: Path, *, directory: bool = False) -> None:
    """소유자 이외의 접근과 symlink를 허용하지 않는다."""
    try:
        info = path.lstat()
    except OSError:
        raise ReleaseError("required private path is unavailable") from None
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ReleaseError("private paths must be root-owned and mode 0700/0600")


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    """동일 파일시스템에서 rename 후 파일·디렉터리를 동기화한다."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def environment(values: dict[str, str], *, raw: bool = False) -> str:
    if raw:
        return "".join(f"{key}={value}\n" for key, value in sorted(values.items()))
    # Compose 단일 인용은 보간을 막는다. newline/NUL은 JSON 검증에서 차단한다.
    return "".join(
        f"{key}='" + value.replace("\\", "\\\\").replace("'", "\\'") + "'\n"
        for key, value in sorted(values.items())
    )


def checked_mapping(value: Any, keys: frozenset[str]) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - keys:
        raise ReleaseError("runtime JSON contains unsupported settings")
    if any(
        not isinstance(item, str) or any(c in item for c in "\r\n\x00")
        for item in value.values()
    ):
        raise ReleaseError("runtime settings must be single-line strings")
    return value


@dataclass(frozen=True)
class Budgets:
    response: int
    drain: int
    worker: int
    uvicorn: int
    stop: int

    @classmethod
    def derive(cls, env: dict[str, str], normal: int, margin: int) -> Budgets:
        try:
            ai = int(env.get("AI_TIMEOUT_SECONDS", "90"))
            cleanup = float(env.get("AI_CLEANUP_TIMEOUT_SECONDS", "5"))
            shutdown = float(env.get("SHUTDOWN_TIMEOUT_SECONDS", "10"))
        except ValueError:
            raise ReleaseError("invalid timeout settings") from None
        if not 10 <= ai <= 300 or not 0.1 <= cleanup <= 30 or not 0.1 <= shutdown <= 30:
            raise ReleaseError("timeout settings exceed product bounds")
        response = math.ceil(max(ai + 9 + cleanup, normal))
        drain = max(30, response + margin)
        worker = drain + 15
        uvicorn = worker + math.ceil(3 * shutdown) + margin
        return cls(response, drain, worker, uvicorn, uvicorn + margin)


@dataclass(frozen=True)
class Runtime:
    root: Path
    project: str
    api_host: str
    data_dir: Path
    mount_path: Path
    filesystem_uuid: str
    config_revision: str
    app_env: dict[str, str]
    migration_env: dict[str, str]
    postgres_env: dict[str, str]
    images: dict[str, str]
    compose: dict[str, str]
    normal_seconds: int
    margin_seconds: int

    @property
    def budgets(self) -> Budgets:
        return Budgets.derive(self.app_env, self.normal_seconds, self.margin_seconds)

    @property
    def host_identity(self) -> str:
        # 앱 설정과 구분해 호스트·DB·프록시 변경을 앱 교체로 적용하지 않는다.
        compose = {
            "NGINX_PROXY_IP": "172.30.0.2",
            "APP_NETWORK_SUBNET": "172.30.0.0/24",
            "DB_NETWORK_SUBNET": "172.31.0.0/24",
            "NGINX_HTTP_PORT": "80",
            "NGINX_HTTPS_PORT": "443",
            "NGINX_BIND_IP": "0.0.0.0",
            **self.compose,
        }
        value = {
            "root": str(self.root),
            "project": self.project,
            "api_host": self.api_host,
            "data_dir": str(self.data_dir),
            "mount": str(self.mount_path),
            "filesystem_uuid": self.filesystem_uuid,
            "images": self.images,
            "postgres_env": self.postgres_env,
            "compose": compose,
        }
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    @classmethod
    def read(cls, path: Path, checkout: Path) -> Runtime:
        private_path(path)
        try:
            value = json.loads(path.read_text())
        except (OSError, ValueError):
            raise ReleaseError("runtime JSON is invalid") from None
        runtime = cls.parse(value, checkout)
        private_path(runtime.root, directory=True)
        private_path(runtime.root / "private", directory=True)
        return runtime

    @classmethod
    def parse(cls, value: Any, checkout: Path) -> Runtime:
        keys = {
            "runtime_dir",
            "project",
            "api_host",
            "postgres_data_dir",
            "postgres_mount_path",
            "postgres_filesystem_uuid",
            "config_revision",
            "app_env",
            "migration_env",
            "postgres_env",
            "images",
            "compose",
            "normal_request_seconds",
            "operational_margin_seconds",
        }
        if not isinstance(value, dict) or set(value) - keys:
            raise ReleaseError("runtime JSON contains unsupported fields")
        try:
            root = Path(value["runtime_dir"])
            data = Path(value["postgres_data_dir"])
            mount = Path(value["postgres_mount_path"])
            project = value["project"]
            host = value["api_host"]
            uuid = value["postgres_filesystem_uuid"]
            revision = value["config_revision"]
            images = value["images"]
            app = checked_mapping(value["app_env"], APP_KEYS)
            migration = checked_mapping(value["migration_env"], MIGRATION_KEYS)
            postgres = checked_mapping(value["postgres_env"], POSTGRES_KEYS)
            compose = checked_mapping(value.get("compose", {}), COMPOSE_KEYS)
            normal = value.get("normal_request_seconds", 30)
            margin = value.get("operational_margin_seconds", 10)
        except (KeyError, TypeError, ValueError):
            raise ReleaseError("runtime JSON is missing required fields") from None
        if not all(isinstance(v, str) for v in (project, host, uuid, revision)):
            raise ReleaseError("runtime identities must be strings")
        if (
            not root.is_absolute()
            or not data.is_absolute()
            or not mount.is_absolute()
            or not data.is_relative_to(mount)
            or data == mount
            or root.resolve().is_relative_to(checkout.resolve())
            or not IDENTIFIER.fullmatch(project)
            or not re.fullmatch(r"(?=.{1,253}$)[a-z0-9]+(?:[.-][a-z0-9]+)*", host)
            or not re.fullmatch(r"[a-fA-F0-9-]{8,64}", uuid)
            or not REVISION.fullmatch(revision)
            or type(normal) is not int
            or not 1 <= normal <= 300
            or type(margin) is not int
            or not 5 <= margin <= 60
        ):
            raise ReleaseError("runtime path, identity or bounds are invalid")
        if (
            not isinstance(images, dict)
            or set(images) != {"nginx", "postgres", "certbot"}
            or any(
                not isinstance(v, str) or not IMAGE.fullmatch(v)
                for v in images.values()
            )
        ):
            raise ReleaseError("infrastructure images must be immutable references")
        if (
            app.get("APP_ENV") != "production"
            or migration.get("APP_ENV") != "production"
        ):
            raise ReleaseError("release requires production settings")
        if (
            not {
                "AI_TIMEOUT_SECONDS",
                "AI_CLEANUP_TIMEOUT_SECONDS",
                "SHUTDOWN_TIMEOUT_SECONDS",
            }
            <= app.keys()
        ):
            raise ReleaseError("release timeout inputs must be explicit")
        try:
            valid_boundary = (
                json.loads(app.get("HTTP_ALLOWED_HOSTS", "null")) == [host]
                and json.loads(app.get("HTTP_TRUSTED_PROXIES", "null"))
                == [compose.get("NGINX_PROXY_IP", "172.30.0.2")]
                and app.get("DATABASE_TLS_CA_FILE") == "/run/config/db-ca.crt"
                and app.get("PASSWORD_BLOCKLIST_PATH")
                == "/run/config/password-blocklist.txt"
                and len(app.get("CSRF_SIGNING_KEY", "").encode()) >= 32
            )
        except ValueError:
            valid_boundary = False
        if not valid_boundary:
            raise ReleaseError("production app boundary settings are invalid")
        database = postgres.get("POSTGRES_DB", "")
        if postgres.get("POSTGRES_USER") != "postgres" or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,62}", database
        ):
            raise ReleaseError("PostgreSQL bootstrap identity is invalid")
        for values, username in (
            (app, "dreamon_app"),
            (migration, "dreamon_migration"),
        ):
            try:
                url = urlsplit(values["DATABASE_URL"])
                valid = (
                    url.scheme == "postgresql+asyncpg"
                    and url.hostname == "postgres"
                    and unquote(url.username or "") == username
                    and url.path == f"/{database}"
                    and not url.query
                    and not url.fragment
                    and url.port in (None, 5432)
                )
            except (KeyError, ValueError):
                valid = False
            if not valid:
                raise ReleaseError(
                    "app and migration must use the scoped PostgreSQL service"
                )
        result = cls(
            root.resolve(),
            project,
            host,
            data.resolve(),
            mount.resolve(),
            uuid,
            revision,
            app,
            migration,
            postgres,
            images,
            compose,
            normal,
            margin,
        )
        Budgets.derive(app, normal, margin)
        return result

    def immutable_environment(self, values: dict[str, str], prefix: str) -> Path:
        contents = environment(values, raw=True)
        digest = hashlib.sha256(contents.encode()).hexdigest()
        target = self.root / "private" / f"{prefix}-{digest}.env"
        if target.exists():
            private_path(target)
            if target.read_text() != contents:
                raise ReleaseError("immutable environment identity mismatch")
        else:
            atomic_write(target, contents)
        return target
