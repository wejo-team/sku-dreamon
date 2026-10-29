"""수동 검사에서 가상 디스크·인증서로 실제 운영 컨테이너 경계를 검증한다.

root와 로컬 Docker daemon이 필요하다. 새 임시 파일에만 파일시스템을 만들며
EBS·운영 설정·유료 모델·공개 ACME는 사용하지 않는다. 결과에는 검사명만 남긴다.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
HOST = "api.example.com"
BLUE_SHA = "a" * 40
GREEN_SHA = "b" * 40


class CheckFailed(Exception):
    """하위 명령의 비밀 입력이나 원문 출력을 포함하지 않는 실패."""


class Harness:
    def __init__(self, temporary: Path) -> None:
        self.temporary = temporary
        self.runtime = temporary / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.private = self.runtime / "private"
        self.private.mkdir(mode=0o700)
        self.config = temporary / "runtime.json"
        self.project = "dep03" + secrets.token_hex(4)
        self.mount_path = temporary / "database"
        self.mount_path.mkdir()
        self.data = self.mount_path / "pgdata"
        self.device: str | None = None
        self.device_link: Path | None = None
        self.mounted = False
        self.checks: list[str] = []
        self.children: list[subprocess.Popen[str]] = []
        self.images: dict[str, str] = {}
        self.values: dict[str, Any] = {}
        self.observations: dict[str, object] = {}
        self.phase = "preflight"
        self.operation = "none"
        self.returncode: int | None = None

    def command(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout: float = 60,
        success: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        self.operation = Path(args[0]).name
        if self.operation == "docker":
            self.operation = "docker:" + next(
                (
                    part
                    for part in args[1:]
                    if part
                    in {
                        "build",
                        "image",
                        "pull",
                        "run",
                        "exec",
                        "inspect",
                        "compose",
                        "network",
                        "ps",
                        "rm",
                        "info",
                    }
                ),
                "operation",
            )
        self.returncode = None
        try:
            result = subprocess.run(
                args,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    "PATH": os.environ["PATH"],
                    "HOME": str(self.temporary),
                    "LANG": "C.UTF-8",
                },
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            raise CheckFailed("bounded child operation failed") from None
        if success and result.returncode:
            self.returncode = result.returncode
            raise CheckFailed("child operation failed")
        return result

    def docker(self, *args: str, **kwargs: Any) -> str:
        return self.command(
            ["docker", "--host", "unix:///var/run/docker.sock", *args], **kwargs
        ).stdout.strip()

    def mark(self, name: str) -> None:
        self.checks.append(name)
        print(f"PASS {name}", flush=True)

    def build(self, name: str, dockerfile: str, context: Path, *build_args: str) -> str:
        tag = f"{self.project}-{name}:test"
        command = ["build", "--quiet", "-t", tag, "-f", str(ROOT / dockerfile)]
        for value in build_args:
            command += ["--build-arg", value]
        self.docker(*command, str(context), timeout=900)
        return self.docker("image", "inspect", tag, "--format", "{{.Id}}")

    def build_images(self) -> None:
        self.phase = "build_production_images"
        self.images["product_blue"] = self.build(
            "product-blue", "backend/Dockerfile", ROOT, f"RELEASE_SHA={BLUE_SHA}"
        )
        self.images["product_green"] = self.build(
            "product-green", "backend/Dockerfile", ROOT, f"RELEASE_SHA={GREEN_SHA}"
        )
        self.images["nginx"] = self.build("nginx", "deploy/nginx/Dockerfile", ROOT)
        self.images["postgres"] = self.build(
            "postgres", "deploy/postgres/Dockerfile", ROOT
        )
        self.docker("pull", "certbot/certbot:v5.8.0", timeout=180)
        self.images["certbot"] = self.docker(
            "image", "inspect", "certbot/certbot:v5.8.0", "--format", "{{.Id}}"
        )
        for color in ("blue", "green"):
            self.images[color] = self.build(
                color,
                "deploy/tests/fixture/Dockerfile",
                ROOT / "deploy/tests/fixture",
                f"BASE_IMAGE={self.project}-product-{color}:test",
            )
        self.images["bad"] = self.build(
            "bad",
            "deploy/tests/fixture/Dockerfile",
            ROOT / "deploy/tests/fixture",
            f"BASE_IMAGE={self.project}-product-green:test",
            "FAIL_READY=1",
        )
        self.docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            self.images["product_blue"],
            "-c",
            "import os,pathlib,importlib.util; assert os.getuid()==10001; "
            "assert not pathlib.Path('/opt/app/tests').exists(); "
            "assert not pathlib.Path('/opt/app/.env').exists(); "
            "assert not pathlib.Path('/opt/app/scripts').exists(); "
            "assert importlib.util.find_spec('pytest') is None; "
            "assert importlib.util.find_spec('ruff') is None; "
            "assert not pathlib.Path('/opt/app/app/product_main.py').exists()",
        )
        self.mark("production_image_nonroot_locked_dependencies_and_no_test_payload")

    def prepare_disk(self) -> None:
        backing = self.temporary / "synthetic-database.img"
        self.command(["truncate", "--size", "512M", str(backing)])
        filesystem_uuid = str(uuid.uuid4())
        self.command(
            ["mkfs.ext4", "-F", "-U", filesystem_uuid, str(backing)], timeout=60
        )
        self.device = self.command(
            ["losetup", "--find", "--show", str(backing)]
        ).stdout.strip()
        if not self.device.startswith("/dev/loop"):
            raise CheckFailed("synthetic loop device was not allocated")
        self.command(["mount", self.device, str(self.mount_path)])
        self.mounted = True
        self.data.mkdir()
        self.device_link = Path("/dev/disk/by-uuid") / filesystem_uuid
        self.device_link.parent.mkdir(parents=True, exist_ok=True)
        if self.device_link.exists() or self.device_link.is_symlink():
            if self.device_link.resolve() != Path(self.device):
                raise CheckFailed("synthetic UUID unexpectedly exists")
        else:
            self.device_link.symlink_to(self.device)
        self.values["postgres_filesystem_uuid"] = filesystem_uuid

    def prepare_certificates(self) -> None:
        # 기존 DB TLS 단위 검사와 같은 단일 self-signed SAN 인증서를 명시적으로 신뢰한다.
        certificate = self.private / "db-ca.crt"
        key = self.private / "postgres.key"
        self.command(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "2",
                "-subj",
                "/CN=postgres",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
                "-addext",
                "subjectAltName=DNS:postgres,DNS:api.example.com",
            ]
        )
        key.chmod(0o600)
        certificate.chmod(0o644)
        shutil.copyfile(certificate, self.private / "postgres.crt")
        self.api_cert, self.api_key = certificate, key

    def prepare_runtime(self) -> None:
        self.phase = "prepare_synthetic_filesystem_and_tls"
        self.prepare_disk()
        self.prepare_certificates()
        passwords: dict[str, str] = {}
        for name in (
            "postgres-bootstrap-password",
            "app-password",
            "migration-password",
        ):
            passwords[name] = "synthetic 'quote\\$ space\"-" + secrets.token_hex(16)
            path = self.private / name
            path.write_text(passwords[name])
            path.chmod(0o600)
        (self.private / "password-blocklist.txt").write_text(
            "blocked-fixture-password\n"
        )
        (self.private / "password-blocklist.txt").chmod(0o644)
        database = "dep03_e2e"
        app_url = f"postgresql+asyncpg://dreamon_app:{quote(passwords['app-password'], safe='')}@postgres:5432/{database}"
        migration_url = f"postgresql+asyncpg://dreamon_migration:{quote(passwords['migration-password'], safe='')}@postgres:5432/{database}"
        common = {
            "APP_ENV": "production",
            "DATABASE_TLS_CA_FILE": "/run/config/db-ca.crt",
        }
        self.values.update(
            {
                "runtime_dir": str(self.runtime),
                "project": self.project,
                "api_host": HOST,
                "postgres_mount_path": str(self.mount_path),
                "postgres_data_dir": str(self.data),
                "config_revision": "synthetic-v1",
                "normal_request_seconds": 5,
                "operational_margin_seconds": 5,
                "images": {
                    name: self.images[name] for name in ("nginx", "postgres", "certbot")
                },
                "postgres_env": {"POSTGRES_USER": "postgres", "POSTGRES_DB": database},
                "migration_env": {**common, "DATABASE_URL": migration_url},
                "app_env": {
                    **common,
                    "DATABASE_URL": app_url,
                    "HTTP_ALLOWED_HOSTS": json.dumps([HOST]),
                    "HTTP_TRUSTED_PROXIES": '["172.30.0.2"]',
                    "AUTH_ALLOWED_ORIGINS": '["https://www.example.com"]',
                    "CSRF_SIGNING_KEY": "synthetic 'quote\\$ space\"-"
                    + secrets.token_hex(32),
                    "PASSWORD_BLOCKLIST_PATH": "/run/config/password-blocklist.txt",
                    "PASSWORD_BLOCKLIST_VERSION": "synthetic-v1",
                    "AI_TIMEOUT_SECONDS": "15",
                    "AI_CLEANUP_TIMEOUT_SECONDS": "1",
                    "SHUTDOWN_TIMEOUT_SECONDS": "1",
                    "OPENAI_API_KEY": "",
                    "AI_REQUIRED": "false",
                },
                "compose": {"NGINX_BIND_IP": "127.0.0.1"},
            }
        )
        self.write_config()

    def write_config(self) -> None:
        self.config.write_text(json.dumps(self.values))
        self.config.chmod(0o600)

    def release(
        self, *args: str, success: bool = True, timeout: float = 180
    ) -> subprocess.CompletedProcess[str]:
        return self.command(
            [
                "python3",
                str(ROOT / "deploy/release.py"),
                "--config",
                str(self.config),
                *args,
            ],
            success=success,
            timeout=timeout,
        )

    def compose(self, *args: str, success: bool = True) -> str:
        return self.docker(
            "compose",
            "--project-directory",
            str(ROOT / "deploy"),
            "--env-file",
            str(self.private / "compose.env"),
            "--project-name",
            self.project,
            "-f",
            str(ROOT / "deploy/compose.production.yaml"),
            "--profile",
            "blue",
            "--profile",
            "green",
            "--profile",
            "tools",
            *args,
            success=success,
        )

    def container(self, service: str) -> dict[str, Any]:
        identity = self.compose("ps", "--all", "--quiet", service)
        return json.loads(self.docker("inspect", identity))[0]

    def status(self) -> dict[str, Any]:
        return json.loads(self.release("status").stdout)

    def wait_healthy(self, service: str, seconds: float = 90) -> None:
        """Docker의 로컬 생존 검사와 별도의 production readiness를 구분한다."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            container = self.container(service)
            state = container["State"]
            if not state["Running"]:
                raise CheckFailed("healthcheck container is not running")
            if state.get("Health", {}).get("Status") == "healthy":
                return
            time.sleep(0.5)
        raise CheckFailed("Docker healthcheck did not become healthy")

    def http(
        self,
        path: str,
        *,
        method: str = "GET",
        data: object = None,
        headers: tuple[str, ...] = (),
        jar: str = "cookies",
        tls: bool = True,
        success: bool = True,
    ) -> tuple[int, dict[str, str], str]:
        body = self.temporary / f"body-{uuid.uuid4()}.txt"
        response_headers = body.with_suffix(".headers")
        cookie = self.temporary / jar
        args = [
            "curl",
            "--silent",
            "--show-error",
            "--max-time",
            "20",
            "--http1.1",
            "--resolve",
            f"{HOST}:{443 if tls else 80}:127.0.0.1",
            "--noproxy",
            "*",
            "--cacert",
            str(self.private / "db-ca.crt"),
            "--request",
            method,
            "--cookie",
            str(cookie),
            "--cookie-jar",
            str(cookie),
            "--output",
            str(body),
            "--dump-header",
            str(response_headers),
            "--write-out",
            "%{http_code}",
            "--header",
            "Connection: close",
        ]
        for header in headers:
            args += ["--header", header]
        if data is not None:
            args += [
                "--header",
                "Content-Type: application/json",
                "--data-binary",
                "@-",
            ]
        args += [f"{'https' if tls else 'http'}://{HOST}{path}"]
        result = self.command(
            args,
            input_text=json.dumps(data) if data is not None else None,
            success=success,
        )
        parsed_headers = {}
        for line in response_headers.read_text().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                parsed_headers[key.lower()] = value.strip()
        return (
            int(result.stdout or "0"),
            parsed_headers,
            body.read_text() if body.exists() else "",
        )

    def wait_pg(self) -> None:
        for _ in range(60):
            result = self.command(
                [
                    "docker",
                    "exec",
                    self.container("postgres")["Id"],
                    "pg_isready",
                    "--host",
                    "postgres",
                    "--username",
                    "postgres",
                    "--dbname",
                    "dep03_e2e",
                ],
                success=False,
            )
            if result.returncode == 0:
                return
            time.sleep(1)
        raise CheckFailed("PostgreSQL did not initialize")

    def safe_diagnostics(self) -> dict[str, object]:
        """명시한 journal 상태와 소유한 migration의 종료 상태만 추출한다."""
        result: dict[str, object] = {}
        try:
            journal = json.loads((self.runtime / "state/release.json").read_text())
            transaction = journal.get("transaction") or {}
            migration = transaction.get("migration") or {}
            for key, value in (
                ("journal_phase", journal.get("phase")),
                ("failure_code", journal.get("failure_code")),
                ("transaction_stage", transaction.get("stage")),
                (
                    "migration_status",
                    migration.get("status")
                    if isinstance(migration, dict)
                    else migration,
                ),
            ):
                if isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,64}", value):
                    result[key] = value
            name = migration.get("name") if isinstance(migration, dict) else None
            if isinstance(name, str) and re.fullmatch(
                re.escape(self.project) + r"-migrate-[a-z0-9-]+", name
            ):
                inspected = self.docker(
                    "inspect", "--format", "{{json .State}}", name, success=False
                )
                if inspected:
                    state = json.loads(inspected)
                    result["migration_running"] = bool(state.get("Running"))
                    result["migration_exit_code"] = state.get("ExitCode")
                    result["migration_oom_killed"] = bool(state.get("OOMKilled"))
                    logs = self.command(
                        ["docker", "logs", "--tail", "100", name], success=False
                    )
                    known_exceptions = (
                        "InvalidPasswordError",
                        "SSLCertVerificationError",
                        "InsufficientPrivilegeError",
                        "ModuleNotFoundError",
                        "PermissionError",
                        "OperationalError",
                        "FileNotFoundError",
                        "InvalidAuthorizationSpecificationError",
                        "ConnectionRefusedError",
                    )
                    result["migration_exception_classes"] = [
                        known
                        for known in known_exceptions
                        if re.search(r"\b" + known + r"\b", logs.stdout + logs.stderr)
                    ]
        except (CheckFailed, OSError, ValueError, AttributeError):
            result["diagnostic_unavailable"] = True
        return result

    def bootstrap(self) -> None:
        self.phase = "bootstrap_http_and_postgres"
        self.release("bootstrap")
        self.wait_pg()
        for service in ("postgres", "nginx"):
            self.wait_healthy(service)
        assert (
            self.docker(
                "exec",
                self.container("nginx")["Id"],
                "curl",
                "--fail",
                "--silent",
                "--max-time",
                "2",
                "http://127.0.0.1:8080/health",
            )
            == "ok"
        )
        self.mark("postgres_and_certificate_free_nginx_docker_healthchecks")
        code, _, _ = self.http("/", tls=False)
        assert code == 308
        challenge = self.runtime / "acme/webroot/.well-known/acme-challenge"
        challenge.mkdir(parents=True, mode=0o755)
        (self.runtime / "acme/webroot").chmod(0o755)
        (challenge / "synthetic-token").write_text("synthetic-challenge")
        code, _, body = self.http(
            "/.well-known/acme-challenge/synthetic-token", tls=False
        )
        assert code == 200 and body == "synthetic-challenge"
        assert not any(
            self.compose("ps", "--quiet", slot) for slot in ("app_blue", "app_green")
        )
        self.mark("certificate_free_http_bootstrap_and_public_http01")
        # 초기 coherent smoke는 임시 CA 인증서로 한다. 공개 ACME 호출은 없다.
        lineage = self.runtime / "acme/letsencrypt/live" / HOST
        lineage.mkdir(parents=True)
        (lineage / "fullchain.pem").write_bytes(self.api_cert.read_bytes())
        shutil.copyfile(self.api_key, lineage / "privkey.pem")
        (lineage / "privkey.pem").chmod(0o600)

    def baseline(self) -> None:
        self.phase = "production_api_migration_tls_and_https"
        self.release(
            "deploy",
            "--image",
            self.images["product_blue"],
            "--sha",
            BLUE_SHA,
            "--migrate",
            timeout=300,
        )
        code, headers, body = self.http("/api/v1/health")
        assert code == 200 and json.loads(body) == {"status": "ok"}
        assert headers["x-release-id"] == BLUE_SHA
        assert headers["x-release-slot"] == "app_blue"
        assert self.http("/api/v1/ready")[0] == 404
        assert self.http("/api/v1/ready/")[0] == 404
        for service in ("postgres", "nginx", "app_blue"):
            self.wait_healthy(service)
        self.observations["baseline_docker_health"] = {
            service: self.container(service)["State"]["Health"]["Status"]
            for service in ("postgres", "nginx", "app_blue")
        }
        self.mark("production_app_liveness_and_private_readiness_are_separate")
        assert (
            self.http(
                "/api/v1/health", headers=("Host: bad.example.com",), success=False
            )[0]
            == 0
        )
        for service in ("postgres", "app_blue"):
            assert not self.container(service)["HostConfig"]["PortBindings"]
        self.pg_id = self.container("postgres")["Id"]
        self.nginx_id = self.container("nginx")["Id"]
        self.mark("production_image_real_postgres_migration_verified_tls_and_https")
        self.phase = "production_cors_preflight"
        code, headers, _ = self.http(
            "/api/v1/auth/csrf",
            method="OPTIONS",
            headers=(
                "Origin: https://www.example.com",
                "Access-Control-Request-Method: POST",
                "Access-Control-Request-Headers: Content-Type,X-CSRF-Token",
            ),
        )
        assert (
            code == 200
            and headers["access-control-allow-origin"] == "https://www.example.com"
        )
        assert headers["access-control-allow-credentials"] == "true"
        self.mark("cors_preflight_survives_proxy_allowlist")
        self.phase = "replace_application_and_verify_proxy"
        self.docker(
            "exec",
            self.pg_id,
            "psql",
            "-U",
            "postgres",
            "-d",
            "dep03_e2e",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE TABLE public.deployment_fixture(value text); "
            "INSERT INTO public.deployment_fixture VALUES ('synthetic-preserved');",
        )
        self.release("deploy", "--image", self.images["green"], "--sha", GREEN_SHA)
        assert self.container("postgres")["Id"] == self.pg_id
        assert self.container("nginx")["Id"] == self.nginx_id
        assert self.http("/api/v1/health")[1]["x-release-slot"] == "app_green"
        assert not self.container("app_blue")["State"]["Running"]
        code, _, body = self.http(
            "/_fixture/peer",
            headers=(
                "Forwarded: for=203.0.113.40;proto=http",
                "X-Forwarded-For: 203.0.113.40",
                "X-Forwarded-Proto: http",
                "X-Forwarded-Host: bad.example.com",
                "X-Forwarded-Unknown: forged",
            ),
        )
        peer = json.loads(body)
        assert code == 200 and peer["scheme"] == "https"
        assert peer["client"] != "203.0.113.40"
        assert set(peer["forwarded"]) == {"x-forwarded-for", "x-forwarded-proto"}
        assert peer["forwarded"]["x-forwarded-for"] == peer["client"]
        self.mark(
            "forged_forwarding_headers_are_replaced_without_rejecting_good_requests"
        )
        self.phase = "rollback_and_database_preservation"
        self.release("rollback")
        assert self.http("/api/v1/health")[1]["x-release-slot"] == "app_blue"
        assert "synthetic-preserved" in self.docker(
            "exec",
            self.pg_id,
            "psql",
            "-U",
            "postgres",
            "-d",
            "dep03_e2e",
            "-Atc",
            "SELECT value FROM public.deployment_fixture",
        )
        self.mark("app_replacement_and_rollback_preserve_database_and_nginx")
        self.phase = "failed_readiness_and_recovery"
        bad = self.release(
            "deploy", "--image", self.images["bad"], "--sha", GREEN_SHA, success=False
        )
        assert bad.returncode != 0
        assert self.status()["failure_code"] == "candidate_not_ready"
        self.wait_healthy("app_green")
        self.observations["failed_candidate_docker_health"] = self.container(
            "app_green"
        )["State"]["Health"]["Status"]
        assert self.http("/api/v1/health")[1]["x-release-slot"] == "app_blue"
        self.mark("candidate_liveness_does_not_bypass_production_readiness_gate")
        self.release("recover")
        assert self.status()["phase"] == "stable"
        self.mark("failed_candidate_readiness_keeps_previous_route_and_recovers")

    def short_sse(self) -> None:
        """짧은 인증 스트림을 받은 구 worker가 끝나야 구 앱이 정지하는지 확인한다."""
        self.phase = "short_authenticated_sse_rollout"
        self.release("deploy", "--image", self.images["green"], "--sha", GREEN_SHA)
        jar = "sse-cookies"

        def csrf() -> str:
            code, _, body = self.http("/api/v1/auth/csrf", jar=jar)
            assert code == 200
            return str(json.loads(body)["data"]["csrfToken"])

        code, _, _ = self.http(
            "/api/v1/accounts",
            method="POST",
            jar=jar,
            headers=("Origin: https://www.example.com", f"X-CSRF-Token: {csrf()}"),
            data={
                "loginId": "dep03" + secrets.token_hex(6),
                "password": "synthetic account " + secrets.token_hex(16),
            },
        )
        assert code == 201
        body = self.temporary / "short-stream.txt"
        headers = self.temporary / "short-stream.headers"
        payload = {
            "requestId": str(uuid.uuid4()),
            "conversationId": str(uuid.uuid4()),
            "clientMessageId": str(uuid.uuid4()),
            "content": "pause:12",
        }
        started = time.monotonic()
        with body.open("w") as output:
            stream = subprocess.Popen(
                [
                    "curl",
                    "--silent",
                    "--fail",
                    "--no-buffer",
                    "--max-time",
                    "45",
                    "--noproxy",
                    "*",
                    "--resolve",
                    f"{HOST}:443:127.0.0.1",
                    "--cacert",
                    str(self.api_cert),
                    "--cookie",
                    str(self.temporary / jar),
                    "--dump-header",
                    str(headers),
                    "--header",
                    "Origin: https://www.example.com",
                    "--header",
                    f"X-CSRF-Token: {csrf()}",
                    "--header",
                    "Content-Type: application/json",
                    "--data-binary",
                    "@-",
                    f"https://{HOST}/api/v1/ai/chat/stream",
                ],
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        self.children.append(stream)
        assert stream.stdin
        stream.stdin.write(json.dumps(payload))
        stream.stdin.close()

        def wait_for(condition: Callable[[], bool], seconds: float) -> None:
            deadline = time.monotonic() + seconds
            while not condition():
                assert time.monotonic() < deadline
                time.sleep(0.1)

        wait_for(
            lambda: (
                "event: answer.delta" in body.read_text() or stream.poll() is not None
            ),
            15,
        )
        assert stream.poll() is None and "event: answer.delta" in body.read_text()
        assert "x-release-slot: app_green" in headers.read_text().lower()
        worker_script = """for p in /proc/[0-9]*; do
if [ -r "$p/cmdline" ] && tr '\\000' ' ' < "$p/cmdline" | grep -q '^nginx: worker process'; then
awk '{print $1 ":" $22}' "$p/stat" || exit 1
fi
done"""

        def workers() -> set[str]:
            return set(
                self.docker("exec", self.nginx_id, "sh", "-ec", worker_script).split()
            )

        old_workers = workers()
        assert old_workers
        master = self.docker("exec", self.nginx_id, "cat", "/proc/1/stat").split()[21]
        rollout = subprocess.Popen(
            [
                "python3",
                str(ROOT / "deploy/release.py"),
                "--config",
                str(self.config),
                "deploy",
                "--image",
                self.images["blue"],
                "--sha",
                BLUE_SHA,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self.children.append(rollout)
        wait_for(
            lambda: self.http("/api/v1/health")[1].get("x-release-slot") == "app_blue",
            20,
        )
        assert rollout.poll() is None and stream.poll() is None
        assert self.container("app_green")["State"]["Running"]
        assert old_workers.intersection(workers())
        assert "event: done" not in body.read_text()
        assert stream.wait(timeout=30) == 0
        assert "event: done" in body.read_text()
        assert ": keepalive" in body.read_text()
        assert rollout.wait(timeout=45) == 0
        old = self.container("app_green")
        assert not old["State"]["Running"] and old["State"]["ExitCode"] == 0
        assert not old_workers.intersection(workers())
        assert self.container("nginx")["Id"] == self.nginx_id
        assert (
            self.docker("exec", self.nginx_id, "cat", "/proc/1/stat").split()[21]
            == master
        )
        assert self.container("postgres")["Id"] == self.pg_id
        self.observations["short_sse_seconds"] = round(time.monotonic() - started, 2)
        for service in ("postgres", "nginx", "app_blue"):
            self.wait_healthy(service)
        self.observations["final_docker_health"] = {
            service: self.container(service)["State"]["Health"]["Status"]
            for service in ("postgres", "nginx", "app_blue")
        }
        self.mark(
            "authenticated_sse_new_slot_before_old_done_then_old_worker_and_app_stop"
        )

    def cleanup(self) -> None:
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
        identities = self.docker(
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={self.project}",
            success=False,
        ).split()
        if identities:
            self.docker("rm", "--force", *identities, timeout=60, success=False)
        networks = self.docker(
            "network",
            "ls",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={self.project}",
            success=False,
        ).split()
        if networks:
            self.docker("network", "rm", *networks, success=False)
        if self.mounted:
            self.command(["umount", str(self.mount_path)], success=False)
        if (
            self.device_link is not None
            and self.device_link.is_symlink()
            and self.device_link.resolve() == Path(self.device or "")
        ):
            self.device_link.unlink()
        if self.device:
            self.command(["losetup", "--detach", self.device], success=False)


def main() -> int:
    if os.geteuid() != 0:
        print(
            "Container E2E requires root for an isolated loopback mount.",
            file=sys.stderr,
        )
        return 1
    report = ROOT / "deploy/test-results/container-e2e.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="dep03-container-") as temporary:
        harness = Harness(Path(temporary))
        success = False
        failure = None
        try:
            harness.observations["docker_version"] = harness.docker(
                "info", "--format", "{{.ServerVersion}}"
            )
            harness.observations["compose_version"] = harness.docker(
                "compose", "version", "--short"
            )
            harness.observations["python_version"] = sys.version.split()[0]
            harness.build_images()
            harness.observations["image_ids"] = dict(harness.images)
            harness.prepare_runtime()
            harness.bootstrap()
            harness.baseline()
            harness.short_sse()
            success = True
        except (
            CheckFailed,
            AssertionError,
            OSError,
            ValueError,
            KeyError,
            subprocess.SubprocessError,
        ) as error:
            failure = type(error).__name__
            print(
                f"FAIL {harness.phase}: {harness.operation} "
                f"returncode={harness.returncode} ({failure})",
                flush=True,
            )
        finally:
            phase, operation, returncode = (
                harness.phase,
                harness.operation,
                harness.returncode,
            )
            diagnostics = harness.safe_diagnostics()
            print("SAFE_STATE " + json.dumps(diagnostics, sort_keys=True), flush=True)
            harness.cleanup()
            report.write_text(
                json.dumps(
                    {
                        "success": success,
                        "checks": harness.checks,
                        "failure_category": failure,
                        "phase": phase,
                        "operation": operation,
                        "returncode": returncode,
                        "state": diagnostics,
                        "observations": harness.observations,
                        "elapsed_seconds": round(time.monotonic() - started, 2),
                    },
                    indent=2,
                )
                + "\n"
            )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
