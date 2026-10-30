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
from release import Release, execute, fingerprint  # noqa: E402

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
            host_identity=runtime.host_identity,
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
            "Config": {
                "Image": record["image"],
                "Env": [
                    f"{key}={value}"
                    for key, value in self.read_environment(
                        Path(record["env_file"])
                    ).items()
                ],
            },
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
        if args[0] in {"update", "stop"}:
            for container in self.actual.values():
                if container["Id"] == args[-1]:
                    if args[0] == "update":
                        if container["State"].get("Restarting"):
                            raise ReleaseError("synthetic update during restart loop")
                        container["restart_policy"] = "no"
                    else:
                        container["State"].update(Running=False, Restarting=False)
        return ""


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.value = settings(Path(self.temporary.name) / "runtime")

    def test_data_directory_must_be_strictly_below_explicit_filesystem_mount(
        self,
    ) -> None:
        for mount, data, valid in (
            ("/", "/var/lib/sku-dreamon/postgres/pgdata", True),
            ("/srv/sku-dreamon-db", "/srv/sku-dreamon-db/pgdata", True),
            ("/", "/", False),
            ("/srv/sku-dreamon-db", "/srv/sku-dreamon-db", False),
            ("/srv/sku-dreamon-db", "/srv/sku-dreamon-db-other/pgdata", False),
            (None, "/var/lib/sku-dreamon/postgres/pgdata", False),
        ):
            value = copy.deepcopy(self.value)
            value["postgres_data_dir"] = data
            if mount is None:
                del value["postgres_mount_path"]
            else:
                value["postgres_mount_path"] = mount
            with self.subTest(mount=mount, data=data):
                if valid:
                    runtime = Runtime.parse(value, DEPLOY.parent)
                    self.assertEqual(str(runtime.mount_path), mount)
                    self.assertEqual(str(runtime.data_dir), data)
                else:
                    with self.assertRaises(ReleaseError):
                        Runtime.parse(value, DEPLOY.parent)

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

    def test_invalid_product_settings_do_not_block_failed_candidate_cleanup(
        self,
    ) -> None:
        self.release.runtime.app_env["AI_MODEL"] = "synthetic-invalid-model"
        docker = self.release.docker

        def command(*args, **kwargs):
            if args[:3] == ("exec", "app_green-id", "python"):
                raise ReleaseError("synthetic Settings validation failure")
            return docker(*args, **kwargs)

        with (
            patch.object(self.release, "docker", side_effect=command),
            patch.object(
                self.release,
                "ready",
                side_effect=lambda slot: Release.verify_slot(self.release, slot),
            ),
        ):
            with self.assertRaisesRegex(ReleaseError, "Settings"):
                self.deploy()
            self.release.recover()
        self.assertEqual(self.release.state["phase"], "stable")
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])
        candidate = self.release.actual["app_green"]
        self.assertFalse(candidate["State"]["Running"])
        self.assertEqual(candidate["restart_policy"], "no")

    def test_failed_exit_and_restart_loop_candidates_are_stopped_on_recovery(
        self,
    ) -> None:
        for running, restarting in ((False, False), (True, True)):
            with self.subTest(running=running, restarting=restarting):
                self.setUp()
                self.release.fail_ready = "app_green"
                with self.assertRaises(ReleaseError):
                    self.deploy()
                candidate = self.release.actual["app_green"]
                candidate["State"].update(
                    Running=running,
                    Restarting=restarting,
                    ExitCode=1,
                    OOMKilled=True,
                )
                self.release.recover()
                self.assertEqual(self.release.state["phase"], "stable")
                self.assertFalse(candidate["State"]["Running"])
                self.assertFalse(candidate["State"]["Restarting"])
                self.assertEqual(candidate["State"]["ExitCode"], 1)
                self.assertEqual(candidate["restart_policy"], "no")
                self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])
                self.assertTrue(self.release.actual["postgres"]["State"]["Running"])

    def test_candidate_cleanup_rejects_image_and_environment_drift(self) -> None:
        for changed in ("image", "environment"):
            with self.subTest(changed=changed):
                self.setUp()
                self.release.fail_ready = "app_green"
                with self.assertRaises(ReleaseError):
                    self.deploy()
                candidate = self.release.actual["app_green"]
                if changed == "image":
                    candidate["Image"] = IMAGE
                else:
                    candidate["Config"]["Env"] = ["AI_MODEL=unmanaged"]
                self.release.events.clear()
                with self.assertRaises(ReleaseError):
                    self.release.recover()
                self.assertFalse(
                    any(
                        event.startswith(("docker:update", "docker:stop"))
                        for event in self.release.events
                    )
                )
                self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])
                self.assertIsNotNone(self.release.state["transaction"])

    def test_candidate_cleanup_refuses_active_slot_or_changed_container(self) -> None:
        self.release.fail_ready = "app_green"
        with self.assertRaises(ReleaseError):
            self.deploy()
        transaction = self.release.state["transaction"]
        transaction["target"] = "app_blue"
        with self.assertRaisesRegex(ReleaseError, "active app"):
            self.release.discard_candidate()
        transaction["target"] = "app_green"
        transaction["candidate_cleanup_id"] = "different-container"
        with self.assertRaisesRegex(ReleaseError, "identity changed"):
            self.release.discard_candidate()
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])

    def test_recovery_before_candidate_recreation_preserves_prior_stopped_slot(
        self,
    ) -> None:
        self.release.worker_plan = [[]]
        self.deploy()
        self.release.runtime.app_env["AI_MODEL"] = "new-settings"
        self.release.configuration_operation = True
        with patch.object(
            self.release,
            "compose_environment",
            side_effect=KeyboardInterrupt("synthetic interruption before up"),
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.release.deploy(NEW_IMAGE, NEW_SHA)
        self.release.events.clear()
        self.release.recover()
        self.assertEqual(self.release.state["active"], "app_green")
        self.assertEqual(self.release.state["phase"], "stable")
        self.assertEqual(self.release.state["slots"]["app_blue"]["sha"], SHA)
        self.assertFalse(self.release.actual["app_blue"]["State"]["Running"])
        self.assertFalse(any(e.startswith("docker:") for e in self.release.events))

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

    def test_same_code_settings_change_requires_configuration_runner(self) -> None:
        self.release.runtime.app_env["AI_REQUESTS_PER_HOUR"] = "12"
        with self.assertRaisesRegex(ReleaseError, "configuration runner"):
            self.release.deploy(IMAGE, SHA)
        self.assertNotIn("app_green", self.release.actual)
        self.release.configuration_operation = True
        self.release.worker_plan = [[]]
        self.release.deploy(IMAGE, SHA)
        self.assertEqual(self.release.state["active"], "app_green")

    def test_same_code_settings_rollback_requires_configuration_runner(self) -> None:
        self.release.configuration_operation = True
        self.release.runtime.app_env["AI_REQUESTS_PER_HOUR"] = "12"
        self.release.worker_plan = [[]]
        self.release.deploy(IMAGE, SHA)
        self.release.configuration_operation = False
        with self.assertRaisesRegex(ReleaseError, "configuration runner"):
            self.release.rollback()
        self.assertEqual(self.release.state["active"], "app_green")
        self.release.configuration_operation = True
        self.release.rollback()
        self.assertEqual(self.release.state["active"], "app_blue")

    def test_same_values_with_new_revision_require_configuration_runner(self) -> None:
        self.release.state["slots"]["app_blue"]["config_revision"] = "prior-revision"
        with self.assertRaisesRegex(ReleaseError, "configuration runner"):
            self.release.deploy(IMAGE, SHA)
        self.assertNotIn("app_green", self.release.actual)

    def test_status_contains_only_safe_identifiers(self) -> None:
        result = json.dumps(self.release.status())
        self.assertNotIn("DATABASE_URL", result)
        self.assertNotIn("synthetic-signing-key", result)
        self.assertNotIn(str(self.release.root), result)

    def test_smoke_retries_until_new_workers_serve_the_expected_release(self) -> None:
        old = (
            "HTTP/1.1 200 OK\r\nX-Release-ID: old\r\n"
            "X-Release-Slot: app_green\r\n\r\n{}"
        )
        expected = (
            f"HTTP/1.1 200 OK\r\nX-Release-ID: {SHA}\r\n"
            "X-Release-Slot: app_blue\r\n\r\n{}"
        )
        with patch.object(
            self.release, "docker", side_effect=[old, expected]
        ) as docker:
            with patch("release.time.sleep"):
                Release.smoke(self.release, "app_blue")
        self.assertEqual(docker.call_count, 2)
        for call in docker.call_args_list:
            self.assertIn("Connection: close", call.args)

    def test_actual_container_environment_drift_is_rejected(self) -> None:
        actual = self.release.actual["app_blue"]
        actual["Config"]["Env"] = [
            f"{key}={value}" for key, value in self.release.runtime.app_env.items()
        ]
        actual["Config"]["Env"] = [
            item
            if not item.startswith("CSRF_SIGNING_KEY=")
            else "CSRF_SIGNING_KEY=changed"
            for item in actual["Config"]["Env"]
        ]
        selected = {
            key: float(value)
            for key, value in self.release.state["slots"]["app_blue"][
                "timeout_env"
            ].items()
        }
        with patch.object(self.release, "docker", return_value=json.dumps(selected)):
            with self.assertRaisesRegex(ReleaseError, "configuration"):
                Release.verify_slot(self.release, "app_blue")

    def test_expired_unobserved_drain_preserves_failure_even_when_workers_are_gone(
        self,
    ) -> None:
        transaction = {
            "nginx": self.release.nginx,
            "workers": ["10:100"],
            "budgets": {"drain": 30},
            "deadline": 0,
        }
        self.release.worker_plan = [[]]
        with self.assertRaisesRegex(ReleaseError, "unproven"):
            self.release.drain(transaction)
        self.assertEqual(
            self.release.state["last_failure"], "worker_drain_deadline_exceeded"
        )
        self.release.drain(transaction, recovering=True)
        self.assertEqual(transaction["failure"], "worker_drain_deadline_exceeded")

    def test_host_lock_loads_the_latest_journal_and_rejects_overlap(self) -> None:
        another = Release(self.release.runtime, DEPLOY.parent)
        with patch("config.private_path"):
            with another.lock():
                self.assertEqual(another.state["active"], "app_blue")
                with self.assertRaisesRegex(ReleaseError, "host lock"):
                    with self.release.lock():
                        self.fail("overlapping lock was acquired")

    def test_pending_configuration_blocks_regular_release_and_certificate_lock(
        self,
    ) -> None:
        pending = self.release.root / "state" / "config-pending.json"
        original = self.release.journal.read_bytes()
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                if symlink:
                    pending.symlink_to(pending.with_name("missing-transaction"))
                else:
                    atomic_write(pending, "{}")
                try:
                    with self.assertRaisesRegex(ReleaseError, "configuration release"):
                        with self.release.lock():
                            self.fail("pending configuration allowed regular operation")
                    self.assertEqual(self.release.journal.read_bytes(), original)
                finally:
                    pending.unlink()

    def test_configuration_runner_can_recover_pending_under_the_same_host_lock(
        self,
    ) -> None:
        pending = self.release.root / "state" / "config-pending.json"
        atomic_write(pending, "{}")
        self.release.configuration_operation = True
        another = Release(self.release.runtime, DEPLOY.parent)
        another.configuration_operation = True
        with patch("config.private_path"):
            with self.release.lock():
                self.assertEqual(self.release.state["active"], "app_blue")
                with self.assertRaisesRegex(ReleaseError, "host lock"):
                    with another.lock():
                        self.fail("configuration recovery bypassed the host lock")

    def test_renewal_commands_disable_sleep_inside_the_host_lock(self) -> None:
        for mode in ("renew", "dry-run"):
            with (
                self.subTest(mode=mode),
                patch.object(self.release, "wait_certificate"),
                patch.object(
                    self.release, "compose", wraps=self.release.compose
                ) as compose,
            ):
                self.release.certificate(mode)
                compose.assert_called_once()
                args = compose.call_args.args
                command = args[args.index("certbot") + 1 :]
                self.assertEqual(command[0], "renew")
                self.assertIn("--no-random-sleep-on-renew", command)
                self.assertEqual("--dry-run" in command, mode == "dry-run")

    def test_initial_certificate_command_has_no_renewal_sleep_option(self) -> None:
        self.release.state.update(phase="bootstrap", active=None, slots={})
        self.release.actual.pop("app_blue")
        with (
            patch.object(self.release, "wait_certificate"),
            patch.object(self.release, "apply_certificate"),
            patch.object(
                self.release, "compose", wraps=self.release.compose
            ) as compose,
        ):
            self.release.certificate("issue", email="operator@example.com")
        compose.assert_called_once()
        args = compose.call_args.args
        command = args[args.index("certbot") + 1 :]
        self.assertEqual(command[0], "certonly")
        self.assertNotIn("--no-random-sleep-on-renew", command)
        self.assertNotIn("--dry-run", command)

    def test_dry_run_does_not_reload_or_claim_a_certificate_installation(self) -> None:
        with patch.object(self.release, "wait_certificate"):
            self.release.certificate("dry-run")
        self.assertEqual(self.release.state["phase"], "stable")
        self.assertNotIn("certificate_digest", self.release.state)
        self.assertFalse(any("reload" in event for event in self.release.events))

    def test_dry_run_marker_mutation_is_a_failure_and_blocks_a_new_deploy(self) -> None:
        def unexpected_install(certificate: dict[str, object]) -> None:
            marker = self.release.root / "state/certbot/installed"
            atomic_write(marker, "1" * 64 + "\n")

        with patch.object(
            self.release, "wait_certificate", side_effect=unexpected_install
        ):
            with self.assertRaisesRegex(ReleaseError, "dry-run"):
                self.release.certificate("dry-run")
        self.assertEqual(self.release.state["phase"], "certificate_failed")
        self.assertEqual(self.release.active_config.read_text(), "old full config\n")
        with self.assertRaisesRegex(ReleaseError, "recover"):
            self.deploy()

    def test_running_certificate_job_blocks_recovery_and_renewal_retry(self) -> None:
        with patch.object(
            self.release, "wait_certificate", side_effect=ReleaseError("still running")
        ):
            with self.assertRaises(ReleaseError):
                self.release.certificate("renew")
        with patch.object(
            self.release,
            "certificate_container",
            return_value={"State": {"Running": True}},
        ):
            with self.assertRaisesRegex(ReleaseError, "still running"):
                self.release.recover()
        with self.assertRaisesRegex(ReleaseError, "recover"):
            self.release.certificate("renew")

    def test_failed_certificate_job_preserves_and_applies_its_installation_event(
        self,
    ) -> None:
        chain = (
            self.release.root
            / "acme/letsencrypt/live"
            / self.release.runtime.api_host
            / "fullchain.pem"
        )
        atomic_write(chain, "unit-only-new-certificate\n")
        atomic_write(chain.with_name("privkey.pem"), "unit-only-key\n")
        installed = fingerprint(chain)
        atomic_write(self.release.root / "state/certbot/installed", installed + "\n")
        self.release.state.update(
            phase="certificate_failed",
            certificate={
                "mode": "renew",
                "stage": "job_failed",
                "prior_phase": "stable",
                "name": "synthetic-certificate-job",
                "nginx": self.release.nginx.copy(),
                "workers": [],
                "old_marker": "1" * 64,
                "budgets": self.release.state["slots"]["app_blue"]["budgets"],
            },
        )
        self.release.worker_plan = [["10:100"], []]
        exited_job = {"State": {"Running": False, "ExitCode": 137, "OOMKilled": True}}
        with (
            patch.object(
                self.release, "certificate_container", return_value=exited_job
            ),
            patch.object(self.release, "verify_certificate") as verify_certificate,
        ):
            self.release.recover()
        reload_event = "docker:exec nginx-original nginx -s reload"
        self.assertEqual(self.release.events.count(reload_event), 1)
        verify_certificate.assert_called_once()
        self.assertEqual(self.release.state["certificate_digest"], installed)
        self.assertEqual(self.release.state["last_failure"], "certificate_job_failed")
        self.assertEqual(self.release.state["phase"], "stable")
        self.assertNotIn("certificate", self.release.state)
        self.assertIn("workers:", self.release.events)
        with patch.object(self.release, "wait_certificate"):
            self.release.certificate("renew")
        self.assertEqual(self.release.events.count(reload_event), 1)

    def test_child_command_failure_never_exposes_secret_arguments_or_output(
        self,
    ) -> None:
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["child", "synthetic-secret"], stderr="synthetic-secret"
        )
        with patch("release.subprocess.run", side_effect=error):
            with self.assertRaises(ReleaseError) as caught:
                execute(["child", "synthetic-secret"])
        self.assertNotIn("synthetic-secret", str(caught.exception))

    def test_first_post_switch_failure_restores_http_bootstrap(self) -> None:
        self.release.state.update(
            phase="bootstrap", active=None, previous=None, slots={}
        )
        self.release.actual.pop("app_blue")
        self.release.fail_smoke = "app_blue"
        self.release.worker_plan = [[]]
        with self.assertRaisesRegex(ReleaseError, "restored"):
            self.deploy()
        self.assertEqual(self.release.active_config.read_text(), "old full config\n")
        self.assertIsNone(self.release.state["active"])
        self.assertFalse(self.release.actual["app_blue"]["State"]["Running"])
        self.release.recover()
        self.assertEqual(self.release.state["phase"], "bootstrap")

    def test_timeout_decrease_still_drains_using_the_old_release_bound(self) -> None:
        prior = dict(self.release.runtime.app_env)
        prior.update(
            AI_TIMEOUT_SECONDS="300",
            AI_CLEANUP_TIMEOUT_SECONDS="30",
            SHUTDOWN_TIMEOUT_SECONDS="30",
        )
        path = self.release.runtime.immutable_environment(prior, "old-release")
        old = self.release.state["slots"]["app_blue"]
        old.update(
            env_file=str(path),
            env_hash=fingerprint(path),
            budgets=asdict(Budgets.derive(prior, 30, 10)),
        )
        self.release.worker_plan = [[]]
        self.deploy()
        self.assertIn("render:app_green:349", self.release.events)
        self.assertEqual(
            self.release.state["slots"]["app_blue"]["budgets"]["drain"], 349
        )
        self.assertIn("AI_TIMEOUT_SECONDS=300", path.read_text())
        self.assertFalse(
            any(
                event.startswith("compose:up") and "postgres" in event
                for event in self.release.events
            )
        )

    def test_changed_infrastructure_is_rejected_before_any_candidate_start(
        self,
    ) -> None:
        self.release.runtime.images["certbot"] = NEW_IMAGE
        with self.assertRaisesRegex(ReleaseError, "host configuration"):
            self.deploy()
        self.assertNotIn("app_green", self.release.actual)


if __name__ == "__main__":
    unittest.main()
