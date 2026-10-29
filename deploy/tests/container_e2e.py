"""CI 전용 가상 디스크·인증서로 실제 운영 컨테이너 경계를 검증한다.

root와 로컬 Docker daemon이 필요하다. 새 임시 파일에만 파일시스템을 만들며
EBS·운영 설정·유료 모델·공개 ACME는 사용하지 않는다. 결과에는 검사명만 남긴다.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
HOST = "api.example.com"
BLUE_SHA = "a" * 40
GREEN_SHA = "b" * 40
BAD_SHA = "c" * 40


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

    def command(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout: float = 60,
        success: bool = True,
    ) -> subprocess.CompletedProcess[str]:
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

    def certificate(self, name: str, hostname: str) -> tuple[Path, Path]:
        key = self.private / f"{name}.key"
        csr = self.private / f"{name}.csr"
        cert = self.private / f"{name}.crt"
        extensions = self.private / f"{name}.ext"
        extensions.write_text(
            f"subjectAltName=DNS:{hostname}\nextendedKeyUsage=serverAuth\n"
        )
        self.command(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                f"/CN={hostname}",
                "-keyout",
                str(key),
                "-out",
                str(csr),
            ]
        )
        self.command(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(self.private / "db-ca.crt"),
                "-CAkey",
                str(self.private / "ca.key"),
                "-CAcreateserial",
                "-days",
                "2",
                "-extfile",
                str(extensions),
                "-out",
                str(cert),
            ]
        )
        key.chmod(0o600)
        cert.chmod(0o644)
        return cert, key

    def prepare_runtime(self) -> None:
        self.prepare_disk()
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
                "/CN=DEP03 synthetic CA",
                "-keyout",
                str(self.private / "ca.key"),
                "-out",
                str(self.private / "db-ca.crt"),
                "-addext",
                "basicConstraints=critical,CA:TRUE",
            ]
        )
        (self.private / "ca.key").chmod(0o600)
        (self.private / "db-ca.crt").chmod(0o644)
        self.certificate("postgres", "postgres")
        self.api_cert, self.api_key = self.certificate("api", HOST)
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
            str(ROOT),
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

    def bootstrap(self) -> None:
        self.release("bootstrap")
        self.wait_pg()
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
        (lineage / "fullchain.pem").write_bytes(
            self.api_cert.read_bytes() + (self.private / "db-ca.crt").read_bytes()
        )
        shutil.copyfile(self.api_key, lineage / "privkey.pem")
        (lineage / "privkey.pem").chmod(0o600)

    def baseline(self) -> None:
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
        bad = self.release(
            "deploy", "--image", self.images["bad"], "--sha", GREEN_SHA, success=False
        )
        assert bad.returncode != 0
        assert self.http("/api/v1/health")[1]["x-release-slot"] == "app_blue"
        self.release("recover")
        assert self.status()["phase"] == "stable"
        self.mark("failed_candidate_readiness_keeps_previous_route_and_recovers")

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
            harness.docker("info", "--format", "{{.ServerVersion}}")
            harness.build_images()
            harness.prepare_runtime()
            harness.bootstrap()
            harness.baseline()
            success = True
        except (CheckFailed, AssertionError, OSError, ValueError, KeyError) as error:
            failure = type(error).__name__
            print(
                f"FAIL container verification ({failure}); private child output withheld",
                flush=True,
            )
        finally:
            harness.cleanup()
            report.write_text(
                json.dumps(
                    {
                        "success": success,
                        "checks": harness.checks,
                        "failure_category": failure,
                        "elapsed_seconds": round(time.monotonic() - started, 2),
                    },
                    indent=2,
                )
                + "\n"
            )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
