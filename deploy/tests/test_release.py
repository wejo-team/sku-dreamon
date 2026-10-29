"""교체 실패·재시도·중단 구간에서 실제 활성 앱과 미완료 드레인을 보존한다."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

from config import (  # noqa: E402
    Budgets,
    ReleaseError,
    Runtime,
    atomic_write,
    environment,
    private_path,
)
from release import Release, fingerprint  # noqa: E402

IMAGE = "sha256:" + "1" * 64
NEW_IMAGE = "sha256:" + "2" * 64
SHA = "a" * 40
NEW_SHA = "b" * 40


def settings(root: Path) -> dict[str, object]:
    return {
        "runtime_dir": str(root),
        "project": "synthetic-release",
        "api_host": "api.example.com",
        "postgres_mount_path": str(root.parent / "mounted"),
        "postgres_data_dir": str(root.parent / "mounted" / "pgdata"),
        "postgres_filesystem_uuid": "12345678-1234-1234-1234-123456789abc",
        "config_revision": "synthetic-1",
        "app_env": {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+asyncpg://dreamon_app:synthetic@postgres/dep03_e2e",
            "DATABASE_TLS_CA_FILE": "/run/config/db-ca.crt",
            "PASSWORD_BLOCKLIST_PATH": "/run/config/password-blocklist.txt",
            "HTTP_ALLOWED_HOSTS": '["api.example.com"]',
            "HTTP_TRUSTED_PROXIES": '["172.30.0.2"]',
            "CSRF_SIGNING_KEY": "synthetic-signing-key-at-least-32-bytes",
            "AI_TIMEOUT_SECONDS": "10",
            "AI_CLEANUP_TIMEOUT_SECONDS": "0.1",
            "SHUTDOWN_TIMEOUT_SECONDS": "0.1",
        },
        "migration_env": {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+asyncpg://dreamon_migration:synthetic@postgres/dep03_e2e",
        },
        "postgres_env": {"POSTGRES_USER": "postgres", "POSTGRES_DB": "dep03_e2e"},
        "images": {"postgres": IMAGE, "nginx": IMAGE, "certbot": IMAGE},
    }


class FakeRelease(Release):
    """외부 명령 경계만 대체하며 journal·전환·복구 엔진은 그대로 실행한다."""

    def __init__(self, runtime: Runtime) -> None:
        super().__init__(runtime, DEPLOY.parent)
        self.events: list[str] = []
        self.worker_calls = 0
        self.worker_plan: list[list[str]] = [["10:100"]]
        self.fail_ready: str | None = None
        self.fail_smoke: str | None = None
        self.fail_config = False
        self.fail_reload = False
        self.crash_stage: str | None = None
        self.nginx = {"id": "nginx-original", "started": "start", "master": "1"}
        self.actual: dict[str, dict[str, object]] = {
            "postgres": {"Id": "database-original", "State": {"Running": True}},
            "nginx": {"Id": "nginx-original", "State": {"Running": True}},
        }
        (self.root / "private").mkdir(parents=True)
        for name in ("db-ca.crt", "password-blocklist.txt"):
            (self.root / "private" / name).write_text("synthetic fixture")
        atomic_write(self.active_config, "old full config\n")
        env = self.runtime.immutable_environment(self.runtime.app_env, "app")
        self.state.update(
            phase="stable",
            active="app_blue",
            previous=None,
            config_hash=fingerprint(self.active_config),
            postgres_id="database-original",
            slots={"app_blue": self.record(IMAGE, SHA, env)},
        )
        self.actual["app_blue"] = self.app_container("app_blue")
        self.save()

    def record(self, image: str, sha: str, env: Path) -> dict[str, object]:
        return {
            "image": image,
            "image_id": image,
            "sha": sha,
            "env_file": str(env),
            "env_hash": fingerprint(env),
            "config_revision": self.runtime.config_revision,
            "budgets": asdict(self.runtime.budgets),
            "timeout_env": {
                key: self.runtime.app_env[key]
                for key in (
                    "AI_TIMEOUT_SECONDS",
                    "AI_CLEANUP_TIMEOUT_SECONDS",
                    "SHUTDOWN_TIMEOUT_SECONDS",
                )
            },
            "asset_hashes": {},
        }

    def app_container(self, slot: str) -> dict[str, object]:
        record = self.state["slots"][slot]
        return {
            "Id": f"{slot}-id",
            "Image": record["image_id"],
            "Config": {"Image": record["image"], "Env": []},
            "State": {"Running": True, "ExitCode": 0, "OOMKilled": False},
        }

    def save(self) -> None:
        transaction = self.state.get("transaction")
        if transaction and transaction["stage"] == self.crash_stage:
            self.crash_stage = None
            raise KeyboardInterrupt("synthetic process interruption")
        super().save()

    def mount(self) -> None:
        self.events.append("mount")

    def image_record(self, image: str, sha: str) -> dict[str, object]:
        env = self.runtime.immutable_environment(self.runtime.app_env, "candidate")
        return self.record(image, sha, env)

    def compose_environment(self) -> None:
        self.events.append("compose_environment")

    def nginx_identity(self) -> dict[str, str]:
        return self.nginx.copy()

    def container(self, service: str) -> dict[str, object] | None:
        return self.actual.get(service)

    def verify_slot(self, slot: str) -> dict[str, object]:
        result = self.container(slot)
        if not result or not result["State"]["Running"]:
            raise ReleaseError("synthetic missing slot")
        return result

    def workers(self, expected: dict[str, str]) -> list[str]:
        if self.nginx_identity() != expected:
            raise ReleaseError("Nginx container or master changed during drain")
        result = self.worker_plan[min(self.worker_calls, len(self.worker_plan) - 1)]
        self.worker_calls += 1
        self.events.append("workers:" + ",".join(result))
        return result

    def ready(self, slot: str, attempts: int = 12) -> None:
        self.events.append(f"ready:{slot}")
        if slot == self.fail_ready:
            raise ReleaseError("synthetic readiness failure")

    def smoke(self, slot: str) -> None:
        self.events.append(f"smoke:{slot}")
        if slot == self.fail_smoke:
            raise ReleaseError("synthetic stale HTTPS route")

    def render(self, slot: str | None, destination: Path, worker_seconds: int) -> None:
        self.events.append(f"render:{slot}:{worker_seconds}")
        atomic_write(destination, f"full config for {slot}\n")

    def test_config(self, candidate: Path) -> None:
        self.events.append("test_config:" + candidate.read_text().strip())
        if self.fail_config:
            raise ReleaseError("synthetic Nginx syntax failure")

    def compose(self, *args: str, **kwargs: object) -> str:
        self.events.append("compose:" + " ".join(args))
        if args[0] == "up":
            slot = args[-1]
            self.actual[slot] = self.app_container(slot)
        elif args[0] == "stop":
            self.actual[args[-1]]["State"]["Running"] = False
        return ""

    def docker(self, *args: str, **kwargs: object) -> str:
        self.events.append("docker:" + " ".join(args))
        if args[-1] == "reload" and self.fail_reload:
            raise ReleaseError("synthetic reload acknowledgement failure")
        return ""


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.value = settings(Path(self.temporary.name) / "runtime")

    def test_raw_env_preserves_dollar_quotes_and_shell_text(self) -> None:
        literal = "dollar$HOME'double\"back\\$(not-a-command)#tail"
        self.assertEqual(
            environment({"CSRF_SIGNING_KEY": literal}, raw=True),
            f"CSRF_SIGNING_KEY={literal}\n",
        )

    def test_unknown_fields_and_multiline_values_fail_closed(self) -> None:
        for mutate in (
            lambda v: v.update({"shell": "source secrets.env"}),
            lambda v: v["app_env"].update({"LD_PRELOAD": "/tmp/inject"}),
            lambda v: v["app_env"].update({"CSRF_SIGNING_KEY": "secret\nAPP_ENV=test"}),
            lambda v: v["images"].update({"nginx": "nginx:latest"}),
            lambda v: v["app_env"].update(
                {"HTTP_TRUSTED_PROXIES": '["172.30.0.0/24"]'}
            ),
        ):
            value = copy.deepcopy(self.value)
            mutate(value)
            with self.subTest(value=list(value)), self.assertRaises(ReleaseError):
                Runtime.parse(value, DEPLOY.parent)

    def test_maximum_budgets_include_shared_cleanup_and_three_lifespan_budgets(
        self,
    ) -> None:
        budgets = Budgets.derive(
            {
                "AI_TIMEOUT_SECONDS": "300",
                "AI_CLEANUP_TIMEOUT_SECONDS": "30",
                "SHUTDOWN_TIMEOUT_SECONDS": "30",
            },
            30,
            10,
        )
        self.assertEqual(budgets.response, 339)
        self.assertEqual(budgets.drain, 349)
        self.assertEqual(budgets.worker, 364)
        self.assertEqual(budgets.uvicorn, 464)
        self.assertEqual(budgets.stop, 474)

    def test_private_path_rejects_nonroot_or_world_readable_files(self) -> None:
        path = Path(self.temporary.name) / "config.json"
        path.write_text("{}")
        path.chmod(0o644)
        with self.assertRaises(ReleaseError):
            private_path(path)


class ReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        value = settings(Path(temporary.name) / "runtime")
        self.release = FakeRelease(Runtime.parse(value, DEPLOY.parent))

    def deploy(self) -> None:
        self.release.deploy(NEW_IMAGE, NEW_SHA)

    def reload_journal(self) -> None:
        self.release.state = json.loads(self.release.journal.read_text())

    def test_candidate_readiness_failure_preserves_active_and_blocks_slot_reuse(
        self,
    ) -> None:
        self.release.fail_ready = "app_green"
        with self.assertRaises(ReleaseError):
            self.deploy()
        self.assertEqual(self.release.active_config.read_text(), "old full config\n")
        self.assertEqual(self.release.state["active"], "app_blue")
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])
        with self.assertRaisesRegex(ReleaseError, "recover"):
            self.deploy()
        self.release.recover()
        self.assertEqual(self.release.state["phase"], "stable")
        self.assertFalse(self.release.actual["app_green"]["State"]["Running"])

    def test_actual_candidate_configuration_is_tested_before_install(self) -> None:
        self.release.fail_config = True
        with self.assertRaises(ReleaseError):
            self.deploy()
        self.assertIn("test_config:full config for app_green", self.release.events)
        self.assertEqual(self.release.active_config.read_text(), "old full config\n")
        self.assertFalse(any("reload" in event for event in self.release.events))

    def test_old_app_stops_only_after_original_worker_identity_exits(self) -> None:
        self.release.worker_plan = [["10:100"], ["10:100"], ["10:100"], ["10:999"]]
        with patch("release.time.sleep"):
            self.deploy()
        self.assertEqual(self.release.state["active"], "app_green")
        stop = next(
            i
            for i, event in enumerate(self.release.events)
            if event.startswith("compose:stop")
        )
        exit_observed = self.release.events.index("workers:10:999")
        self.assertGreater(stop, exit_observed)
        self.assertTrue(self.release.actual["app_green"]["State"]["Running"])

    def test_switch_failure_restores_previous_and_drains_candidate_before_stop(
        self,
    ) -> None:
        self.release.fail_smoke = "app_green"
        self.release.worker_plan = [["10:100"], ["10:100"], ["10:100", "11:101"], []]
        with self.assertRaisesRegex(ReleaseError, "restored"):
            self.deploy()
        self.assertEqual(self.release.active_config.read_text(), "old full config\n")
        self.assertEqual(self.release.state["active"], "app_blue")
        self.assertEqual(self.release.state["transaction"]["stage"], "restored")
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])
        self.assertFalse(self.release.actual["app_green"]["State"]["Running"])
        self.release.recover()
        self.assertEqual(self.release.state["phase"], "stable")

    def test_interruption_between_atomic_config_and_journal_recovers_forward(
        self,
    ) -> None:
        self.release.crash_stage = "reload_pending"
        with self.assertRaises(KeyboardInterrupt):
            self.deploy()
        self.reload_journal()
        self.assertEqual(self.release.state["transaction"]["stage"], "config_intent")
        self.assertEqual(
            self.release.active_config.read_text(), "full config for app_green\n"
        )
        self.release.worker_plan = [[], []]
        self.release.worker_calls = 0
        self.release.recover()
        self.assertEqual(self.release.state["active"], "app_green")
        self.assertEqual(self.release.state["phase"], "stable")

    def test_reload_failure_can_be_retried_without_overwriting_unknown_config(
        self,
    ) -> None:
        self.release.fail_reload = True
        with self.assertRaises(ReleaseError):
            self.deploy()
        atomic_write(self.release.active_config, "unmanaged drift\n")
        with self.assertRaisesRegex(ReleaseError, "refuses"):
            self.release.recover()
        self.assertEqual(self.release.active_config.read_text(), "unmanaged drift\n")

    def test_nginx_recreation_is_not_treated_as_successful_worker_exit(self) -> None:
        self.release.fail_reload = True
        with self.assertRaises(ReleaseError):
            self.deploy()
        self.release.nginx["id"] = "new-nginx-container"
        with self.assertRaisesRegex(ReleaseError, "Nginx identity"):
            self.release.recover()
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])

    def test_unfinished_migration_blocks_recovery_and_a_second_deploy(self) -> None:
        self.release.fail_ready = "app_green"
        with self.assertRaises(ReleaseError):
            self.deploy()
        transaction = self.release.state["transaction"]
        transaction["migration"] = {"name": "synthetic-migrate", "status": "starting"}
        with patch.object(
            self.release,
            "migration_container",
            return_value={"State": {"Running": True}},
        ):
            with self.assertRaisesRegex(ReleaseError, "migration is still running"):
                self.release.recover()
        with self.assertRaisesRegex(ReleaseError, "recover"):
            self.deploy()
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])

    def test_recovery_preserves_failed_forced_stop_evidence(self) -> None:
        self.release.worker_plan = [[], []]
        self.release.crash_stage = "cleanup"
        with self.assertRaises(KeyboardInterrupt):
            self.deploy()
        self.reload_journal()
        self.release.actual["app_blue"]["State"].update(Running=False, ExitCode=137)
        with self.assertRaisesRegex(ReleaseError, "graceful stop"):
            self.release.recover()
        self.assertNotEqual(self.release.state["phase"], "stable")

    def test_db_target_or_csrf_rotation_is_rejected_before_starting_candidate(
        self,
    ) -> None:
        self.release.runtime.app_env["CSRF_SIGNING_KEY"] = (
            "another-synthetic-secret-at-least-32-bytes"
        )
        with self.assertRaisesRegex(ReleaseError, "rotation"):
            self.deploy()
        self.assertNotIn("app_green", self.release.actual)

    def test_status_contains_only_safe_identifiers(self) -> None:
        result = json.dumps(self.release.status())
        self.assertNotIn("DATABASE_URL", result)
        self.assertNotIn("synthetic-signing-key", result)
        self.assertNotIn(str(self.release.root), result)


if __name__ == "__main__":
    unittest.main()
