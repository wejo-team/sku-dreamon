"""운영 프록시와 DB 기동 보호의 실패 경계를 실제 명령으로 확인한다."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
SPEC = importlib.util.spec_from_file_location(
    "nginx_renderer", DEPLOY / "nginx/render.py"
)
assert SPEC and SPEC.loader
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)
SHA = "a" * 40
UUID = "00000000-0000-4000-8000-000000000001"


class NginxRendererTests(unittest.TestCase):
    def render(self, **overrides: object) -> str:
        args = {
            "host": "api.example.com",
            "slot": "app_blue",
            "release": SHA,
            "drain_seconds": 150,
            "tls": True,
        }
        args.update(overrides)
        return str(RENDERER.render_config(**args))

    def test_bootstrap_starts_without_certificates_or_app_dns(self) -> None:
        config = self.render(tls=False)
        self.assertNotIn("ssl_certificate", config)
        self.assertNotIn("listen 443", config)
        self.assertNotIn("upstream", config)
        self.assertIn("/.well-known/acme-challenge/", config)
        self.assertIn("return 308 https://api.example.com$request_uri", config)
        self.assertIn("listen 80 default_server", config)
        self.assertIn("return 444", config)

    def test_only_selected_slot_and_current_release_are_emitted(self) -> None:
        config = self.render(slot="app_green")
        self.assertTrue(config.startswith(f"# release:{SHA} slot:app_green\n"))
        self.assertIn("server app_green:8000", config)
        self.assertNotIn("app_blue", config)
        self.assertIn(f"add_header X-Release-ID {SHA} always;", config)
        self.assertIn("add_header X-Release-Slot app_green always;", config)
        self.assertIn("proxy_hide_header X-Release-ID", config)

    def test_proxy_drops_unlisted_headers_and_preserves_browser_contract(self) -> None:
        config = self.render()
        self.assertIn("proxy_pass_request_headers off;", config)
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", config)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", config)
        for header in (
            "Cookie",
            "Origin",
            "Referer",
            "X-CSRF-Token",
            "Content-Type",
            "Access-Control-Request-Method",
            "Access-Control-Request-Headers",
        ):
            self.assertIn(f"proxy_set_header {header} ", config)
        self.assertNotIn("$proxy_add_x_forwarded_for", config)
        self.assertNotIn("proxy_set_header Content-Length", config)
        self.assertIn("location = /api/v1/ready { return 404; }", config)
        self.assertIn("location ^~ /api/v1/ready/ { return 404; }", config)
        self.assertIn("ssl_reject_handshake on;", config)

    def test_sse_is_unbuffered_and_old_workers_have_larger_budget(self) -> None:
        config = self.render(drain_seconds=360)
        self.assertIn("worker_shutdown_timeout 375s;", config)
        self.assertIn("proxy_read_timeout 360s;", config)
        for directive in (
            "proxy_buffering off",
            "proxy_request_buffering off",
            "proxy_cache off",
            "proxy_next_upstream off",
            "gzip off",
        ):
            self.assertIn(directive + ";", config)

    def test_configuration_injection_and_unbounded_timeouts_fail(self) -> None:
        invalid = [
            {"host": "api.example.com; return 200"},
            {"host": "api.example.com\nserver{}"},
            {"host": "*.example.com"},
            {"host": "localhost"},
            {"host": "a..example.com"},
            {"host": "API.example.com"},
            {"slot": "app_green;"},
            {"release": "a" * 39},
            {"release": "a" * 39 + "\n"},
            {"drain_seconds": 10},
            {"drain_seconds": 1801},
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.render(**value)

    def test_cli_refuses_bad_input_without_truncating_existing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.conf"
            candidate.write_text("existing candidate", encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    str(DEPLOY / "nginx/render.py"),
                    "--host",
                    "*",
                    "--slot",
                    "app_blue",
                    "--release",
                    SHA,
                    "--drain-seconds",
                    "150",
                    "--output",
                    str(candidate),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(candidate.read_text(), "existing candidate")


class PostgresMountTests(unittest.TestCase):
    def test_both_uuid_and_actual_device_must_match(self) -> None:
        cases = [
            ((UUID, UUID, "259:1", "259:1"), True),
            ((UUID, "other", "259:1", "259:1"), False),
            ((UUID, UUID, "259:1", "8:1"), False),
            (("", "", "259:1", "259:1"), False),
            ((UUID, UUID, "", ""), False),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                result = subprocess.run(
                    ["sh", str(DEPLOY / "postgres/check-identity.sh"), *args],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode == 0, expected)
                self.assertEqual(result.stdout, "")
                self.assertNotIn(UUID, result.stderr)

    def check_host(
        self, *, actual_uuid: str = UUID, nested: bool = False, missing: bool = False
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mount = root / "db"
            data = mount / "pgdata"
            data.mkdir(parents=True)
            fake = root / "bin"
            fake.mkdir()
            findmnt = fake / "findmnt"
            findmnt.write_text(
                "#!/bin/sh\n"
                + (
                    "exit 1\n"
                    if missing
                    else f"case \"$*\" in\n*UUID) printf '%s\\n' '{actual_uuid}';;\n"
                    + ("*pgdata*) printf '8:1\\n';;\n" if nested else "")
                    + "*) printf '259:1\\n';;\nesac\n"
                ),
                encoding="utf-8",
            )
            findmnt.chmod(0o755)
            return subprocess.run(
                [
                    "sh",
                    str(DEPLOY / "postgres/check-mount.sh"),
                    str(mount),
                    UUID,
                    str(data),
                ],
                env={"PATH": f"{fake}:{os.defpath}"},
                capture_output=True,
                text=True,
                check=False,
            )

    def test_host_checks_fail_for_missing_wrong_or_nested_filesystem(self) -> None:
        self.assertEqual(self.check_host().returncode, 0)
        for overrides in (
            {"actual_uuid": "wrong"},
            {"nested": True},
            {"missing": True},
        ):
            with self.subTest(overrides=overrides):
                result = self.check_host(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotIn(UUID, result.stderr)

    def test_container_guard_refuses_missing_contract_before_postgres(self) -> None:
        result = subprocess.run(
            ["sh", str(DEPLOY / "postgres/guard-entrypoint.sh"), "postgres"],
            env={"PATH": os.defpath},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("validation failed", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_pg_tls_and_roles_never_allow_plaintext_tcp(self) -> None:
        hba = (DEPLOY / "postgres/pg_hba.conf").read_text()
        self.assertLess(hba.index("hostnossl all all all reject"), hba.index("hostssl"))
        self.assertIn("hostssl all dreamon_app all scram-sha-256", hba)
        self.assertIn("host all all all reject", hba)
        config = (DEPLOY / "postgres/postgresql.conf").read_text()
        self.assertIn("ssl = on", config)
        self.assertIn("log_min_error_statement = 'panic'", config)
        roles = (DEPLOY / "postgres/init-roles.sh").read_text()
        self.assertIn("\\getenv app_password APP_DB_PASSWORD", roles)
        self.assertIn("PASSWORD :'app_password'", roles)
        self.assertIn("ALTER DEFAULT PRIVILEGES FOR ROLE dreamon_migration", roles)
        self.assertNotIn("--set app_password", roles)


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI is required")
class ComposeContractTests(unittest.TestCase):
    def test_parse_preserves_literal_credentials_and_isolates_services(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            private = runtime / "private"
            private.mkdir()
            for name in (
                "app-blue.env",
                "app-green.env",
                "migrate.env",
                "postgres.env",
                "postgres-bootstrap-password",
                "app-password",
                "migration-password",
            ):
                (private / name).write_text("SYNTHETIC_SECRET=a$B'c\\d\"\n")
            environment = {
                "PATH": os.environ["PATH"],
                "HOME": directory,
                "RUNTIME_DIR": directory,
                "APP_BLUE_IMAGE": "example.com/api@sha256:" + "1" * 64,
                "APP_GREEN_IMAGE": "example.com/api@sha256:" + "2" * 64,
                "MIGRATION_IMAGE": "example.com/api@sha256:" + "2" * 64,
                "NGINX_IMAGE": "example.com/nginx@sha256:" + "3" * 64,
                "POSTGRES_IMAGE": "example.com/postgres@sha256:" + "4" * 64,
                "APP_BLUE_ENV_FILE": str(private / "app-blue.env"),
                "APP_GREEN_ENV_FILE": str(private / "app-green.env"),
                "MIGRATION_ENV_FILE": str(private / "migrate.env"),
                "POSTGRES_ENV_FILE": str(private / "postgres.env"),
                "POSTGRES_FILESYSTEM_UUID": UUID,
                "POSTGRES_DATA_DIR": str(runtime / "pgdata"),
            }
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(DEPLOY / "compose.production.yaml"),
                    "--profile",
                    "blue",
                    "--profile",
                    "green",
                    "--profile",
                    "tools",
                    "config",
                    "--format",
                    "json",
                ],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            services = json.loads(result.stdout)["services"]
            for name in ("app_blue", "app_green", "postgres", "migrate"):
                self.assertNotIn("ports", services[name])
                # config 출력은 재입력 시 보간을 피하도록 $를 $$로 직렬화한다.
                literal = services[name]["environment"]["SYNTHETIC_SECRET"]
                self.assertEqual(literal.replace("$$", "$"), "a$B'c\\d\"")
            self.assertEqual(services["app_blue"]["profiles"], ["blue"])
            self.assertEqual(services["app_green"]["profiles"], ["green"])
            self.assertEqual(set(services["nginx"]["networks"]), {"edge"})
            self.assertEqual(set(services["postgres"]["networks"]), {"database"})
            self.assertEqual(set(services["migrate"]["networks"]), {"database"})
            postgres = services["postgres"]
            self.assertEqual(postgres["devices"][0]["permissions"], "r")
            for service in services.values():
                for volume in service.get("volumes", []):
                    self.assertFalse(volume["bind"]["create_host_path"])


if __name__ == "__main__":
    unittest.main()
