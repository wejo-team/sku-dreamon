"""같은 이미지의 설정 전환과 실패·중단 후 실행 상태 및 원본 입력의 복구를 검사한다."""

from __future__ import annotations

import contextlib
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import cd_release as cd  # noqa: E402
from config import Runtime, atomic_write  # noqa: E402
from config_release import ConfigError, ConfigRelease, env_hash  # noqa: E402
from ssm_config import Snapshot, SourceError  # noqa: E402
from test_release import SHA, FakeRelease, settings  # noqa: E402


class SourceFixture:
    def __init__(self, app_env):
        self.app_env = app_env
        self.calls = []
        self.failure = False

    def fetch(self, version, runner):
        self.calls.append(version)
        if self.failure:
            raise SourceError("ssm_read_failed")
        return Snapshot(copy.deepcopy(self.app_env), f"ssm-{version}-synthetic", {})


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        root = self.base / "runtime"
        self.original = settings(root)
        self.release = FakeRelease(Runtime.parse(self.original, DEPLOY.parent))
        root.chmod(0o700)
        self.release.worker_plan = [["10:100"], []]
        self.runtime_path = self.base / "runtime.json"
        atomic_write(self.runtime_path, json.dumps(self.original))
        releases = self.base / "releases"
        releases.mkdir()
        (releases / SHA).mkdir()
        self.current = self.base / "current"
        self.current.symlink_to(releases / SHA)
        self.config = cd.Config(
            "ap-northeast-2",
            "synthetic-artifacts",
            "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/synthetic-app",
            self.runtime_path,
            releases,
            self.current,
        )
        self.source = SourceFixture(copy.deepcopy(self.original["app_env"]))
        self.source.app_env.update(
            OPENAI_API_KEY="synthetic-secret", AI_REQUESTS_PER_HOUR="11"
        )

        @contextlib.contextmanager
        def factory(config, checkout):
            self.release.checkout = checkout
            self.release.runtime = Runtime.parse(
                json.loads(config.runtime_config.read_text()), checkout
            )
            yield self.release

        self.factory = factory
        self.operation = ConfigRelease(
            self.config,
            self.base / "ssm-config.json",
            engine_factory=factory,
            source_factory=lambda path: self.source,
        )
        self.addCleanup(patch.stopall)
        patch(
            "config.private_path",
            side_effect=lambda path, **kw: cd.trusted(path, private=True, **kw),
        ).start()

    def change(self, action="apply", version=1):
        status = self.operation.status()
        return self.operation.change(
            action,
            status["active_sha"],
            status["active_env_hash"],
            status["active_config_revision"],
            version,
        )

    def assert_original(self):
        self.assertEqual(json.loads(self.runtime_path.read_text()), self.original)
        record = self.release.state["slots"][self.release.state["active"]]
        self.assertEqual(record["env_hash"], env_hash(self.original["app_env"]))
        self.assertEqual(record["config_revision"], self.original["config_revision"])
        self.assertEqual(record["sha"], SHA)
        self.assertEqual(self.release.state["phase"], "stable")
        self.assertFalse(self.operation.pending.exists())
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])

    def test_same_image_and_code_are_recreated_with_exact_snapshot(self):
        image = self.release.state["slots"]["app_blue"]["image"]
        result = self.change(version=3)
        record = self.release.state["slots"]["app_green"]
        self.assertEqual((record["sha"], record["image"]), (SHA, image))
        self.assertEqual(self.source.calls, [3])
        self.assertEqual(record["config_revision"], "ssm-3-synthetic")
        self.assertEqual(
            json.loads(self.runtime_path.read_text())["app_env"], self.source.app_env
        )
        self.assertEqual(result["operation_status"], "applied")
        self.assertFalse(self.operation.pending.exists())
        self.assertEqual(self.release.actual["postgres"]["Id"], "database-original")
        self.assertEqual(self.current.resolve().name, SHA)
        self.assertFalse(any("migrate" in event for event in self.release.events))

    def test_exact_repeated_version_is_noop_but_new_version_redeploys(self):
        self.change()
        self.release.events.clear()
        self.assertEqual(self.change()["operation_status"], "unchanged")
        self.assertFalse(
            any(event.startswith("compose:up") for event in self.release.events)
        )
        self.assertEqual(self.change(version=2)["operation_status"], "applied")

    def test_langsmith_settings_apply_and_rollback_without_exposing_key(self):
        self.source.app_env.update(
            LANGSMITH_TRACING="false",
            LANGSMITH_API_KEY="synthetic-tracing-secret",
            LANGSMITH_PROJECT="sku-dreamon-test",
            LANGSMITH_ENDPOINT="https://api.smith.langchain.com",
            LANGSMITH_WORKSPACE_ID="00000000-0000-4000-8000-000000000001",
            LANGSMITH_HIDE_INPUTS="true",
            LANGSMITH_HIDE_OUTPUTS="false",
        )
        result = self.change()
        self.assertEqual(result["operation_status"], "applied")
        self.assertEqual(
            json.loads(self.runtime_path.read_text())["app_env"], self.source.app_env
        )
        self.assertNotIn(
            "synthetic-tracing-secret", json.dumps(self.operation.status())
        )
        self.change("rollback", 0)
        self.assert_original()

    def test_manual_rollback_restores_original_runtime_and_container(self):
        self.change()
        self.source.failure = True
        result = self.change("rollback", 0)
        self.assertEqual(result["operation_status"], "rolled_back")
        self.assert_original()
        self.assertEqual(self.source.calls, [1])

    def test_following_code_release_uses_successful_or_restored_configuration(self):
        self.change()
        self.assertFalse(
            self.operation.cd.guard(self.release, SHA, "b" * 40, "sha256:" + "2" * 64)
        )
        self.change("rollback", 0)
        self.assertFalse(
            self.operation.cd.guard(self.release, SHA, "b" * 40, "sha256:" + "2" * 64)
        )
        self.assert_original()

    def test_candidate_readiness_failure_restores_without_publishing_bad_input(self):
        self.release.fail_ready = "app_green"
        with self.assertRaisesRegex(ConfigError, "configuration_failed_restored"):
            self.change()
        self.assert_original()
        self.assertFalse(self.release.actual["app_green"]["State"]["Running"])

    def test_post_switch_smoke_failure_restores_both_runtime_and_routing(self):
        self.release.fail_smoke = "app_green"
        with self.assertRaisesRegex(ConfigError, "configuration_failed_restored"):
            self.change()
        self.assert_original()
        self.assertIn("smoke:app_blue", self.release.events)

    def test_failed_runtime_publication_rolls_back_completed_transition(self):
        publish = self.operation.publish
        failed = False

        def fail_once(value, allowed):
            nonlocal failed
            if not failed:
                failed = True
                raise OSError("synthetic publication failure")
            return publish(value, allowed)

        with patch.object(self.operation, "publish", side_effect=fail_once):
            with self.assertRaisesRegex(ConfigError, "configuration_failed_restored"):
                self.change()
        self.assert_original()

    def test_process_interruption_before_candidate_recovers_using_persisted_state(self):
        self.release.crash_stage = "candidate_started"
        with self.assertRaises(KeyboardInterrupt):
            self.change()
        self.assertTrue(self.operation.pending.exists())
        self.source.failure = True
        self.change("recover", 0)
        self.assert_original()

    def test_process_interruption_after_commit_restores_original_on_recover(self):
        with patch.object(
            self.operation, "clear_pending", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.change()
        self.assertEqual(self.operation.status()["config_phase"], "pending")
        self.assertEqual(
            json.loads(self.runtime_path.read_text())["config_revision"],
            "ssm-1-synthetic",
        )
        self.change("recover", 0)
        self.assert_original()

    def test_unrecoverable_failure_keeps_evidence_and_blocks_code_cd(self):
        self.release.crash_stage = "reload_pending"
        with self.assertRaises(KeyboardInterrupt):
            self.change()
        self.release.nginx["id"] = "unknown-nginx"
        with self.assertRaisesRegex(ConfigError, "configuration_recovery_required"):
            self.change("recover", 0)
        self.assertTrue(self.operation.pending.exists())
        with self.assertRaisesRegex(cd.CDError, "configuration_recovery_required"):
            self.operation.cd.stable(self.release)
        with self.assertRaisesRegex(ConfigError, "configuration_recovery_required"):
            self.change(version=2)

    def test_unhealthy_candidate_after_interrupted_cutover_restores_old_route(self):
        self.release.crash_stage = "cleanup"
        with self.assertRaises(KeyboardInterrupt):
            self.change()
        self.release.fail_ready = "app_green"
        self.change("recover", 0)
        self.assert_original()
        self.assertEqual(self.release.active_config.read_text(), "old full config\n")

    def test_interrupted_cleanup_can_restart_known_old_container(self):
        self.release.crash_stage = "cleanup"
        with self.assertRaises(KeyboardInterrupt):
            self.change()
        self.release.actual["app_blue"]["State"]["Running"] = False
        self.release.fail_ready = "app_green"
        self.change("recover", 0)
        self.assert_original()

    def test_pending_delete_fsync_failure_does_not_lose_rollback_record(self):
        synchronize = self.operation.cd.sync_directory
        calls = 0

        def fail_once(path):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("synthetic directory fsync failure")
            return synchronize(path)

        with patch.object(self.operation.cd, "sync_directory", side_effect=fail_once):
            with self.assertRaisesRegex(ConfigError, "configuration_failed_restored"):
                self.change()
        self.assert_original()

    def test_persistent_pending_delete_failure_keeps_recovery_block(self):
        with patch.object(self.operation.cd, "sync_directory", side_effect=OSError):
            with self.assertRaisesRegex(ConfigError, "configuration_recovery_required"):
                self.change()
        self.assertTrue(self.operation.pending.exists())
        self.assertEqual(json.loads(self.runtime_path.read_text()), self.original)
        self.change("recover", 0)
        self.assert_original()

    def test_ssm_failure_has_no_local_mutations(self):
        self.source.failure = True
        with self.assertRaises(SourceError):
            self.change()
        self.assert_original()
        self.assertFalse(
            any(event.startswith("compose:up") for event in self.release.events)
        )

    def test_protected_values_and_missing_required_values_are_rejected(self):
        for key in (
            "DATABASE_URL",
            "CSRF_SIGNING_KEY",
            "HTTP_ALLOWED_HOSTS",
            "PASSWORD_BLOCKLIST_PATH",
            "AUTH_ALLOWED_ORIGINS",
        ):
            with self.subTest(key=key):
                self.source.app_env = copy.deepcopy(self.original["app_env"])
                self.source.app_env[key] = "synthetic changed value"
                with self.assertRaisesRegex(
                    ConfigError, "setting_requires_separate_procedure"
                ):
                    self.change()
                self.assert_original()

    def test_rollback_to_different_code_is_refused(self):
        self.change()
        previous = self.release.state["previous"]
        self.release.state["slots"][previous]["sha"] = "b" * 40
        self.release.save()
        with self.assertRaisesRegex(ConfigError, "previous_configuration_unavailable"):
            self.change("rollback", 0)

    def test_stale_revision_rejects_even_when_environment_values_match(self):
        before = self.operation.status()
        self.change()
        same_env = self.operation.status()["active_env_hash"]
        self.change(version=2)
        with self.assertRaisesRegex(ConfigError, "current_configuration_changed"):
            self.operation.change("apply", SHA, same_env, "ssm-1-synthetic", 3)
        with self.assertRaisesRegex(ConfigError, "current_configuration_changed"):
            self.operation.change(
                "apply",
                SHA,
                before["active_env_hash"],
                before["active_config_revision"],
                3,
            )

    def test_manual_runtime_drift_is_not_overwritten(self):
        value = copy.deepcopy(self.original)
        value["app_env"]["AI_REQUESTS_PER_HOUR"] = "99"
        atomic_write(self.runtime_path, json.dumps(value))
        with self.assertRaisesRegex(
            ConfigError, "runtime_does_not_match_active_release"
        ):
            self.change()
        self.assertEqual(json.loads(self.runtime_path.read_text()), value)

    def test_snapshot_tampering_blocks_recovery(self):
        self.release.crash_stage = "candidate_started"
        with self.assertRaises(KeyboardInterrupt):
            self.change()
        pending = json.loads(self.operation.pending.read_text())
        path = self.operation.snapshot_path(pending["old_snapshot"])
        atomic_write(path, "{}\n")
        with self.assertRaisesRegex(ConfigError, "configuration_recovery_required"):
            self.change("recover", 0)
        self.assertTrue(self.operation.pending.exists())

    def test_status_and_journal_do_not_expose_values(self):
        self.release.crash_stage = "candidate_started"
        with self.assertRaises(KeyboardInterrupt):
            self.change()
        text = json.dumps(self.operation.status()) + self.operation.pending.read_text()
        self.assertNotIn("synthetic-secret", text)
        self.assertNotIn(self.original["app_env"]["DATABASE_URL"], text)
        for path in self.operation.cd.root.glob("private/config-*.json"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_unknown_runtime_after_crash_requires_manual_reconciliation(self):
        self.release.crash_stage = "candidate_started"
        with self.assertRaises(KeyboardInterrupt):
            self.change()
        value = copy.deepcopy(self.original)
        value["normal_request_seconds"] = 25
        atomic_write(self.runtime_path, json.dumps(value))
        with self.assertRaisesRegex(ConfigError, "configuration_recovery_required"):
            self.change("recover", 0)
        self.assertEqual(json.loads(self.runtime_path.read_text()), value)

    def test_pending_operation_blocks_backup(self):
        import backup

        atomic_write(self.operation.pending, "{}")
        options = backup.Options("synthetic-backups", "ap-northeast-2")
        job = backup.Backup(
            self.release.runtime, self.runtime_path, DEPLOY.parent, options
        )
        with self.assertRaisesRegex(backup.BackupError, "release_not_stable"):
            with job.release_lock():
                self.fail("pending configuration must not be archived as stable")

    def test_code_cd_cannot_roll_back_configuration_without_runtime_publication(self):
        self.change()
        with self.assertRaisesRegex(
            cd.CDError, "configuration_requires_dedicated_release"
        ):
            self.operation.cd.change("rollback", SHA, SHA)
        self.assertEqual(
            self.operation.status()["active_config_revision"], "ssm-1-synthetic"
        )

    def test_code_cd_cannot_silently_apply_manually_changed_runtime(self):
        value = copy.deepcopy(self.original)
        value["app_env"]["AI_REQUESTS_PER_HOUR"] = "99"
        self.release.runtime = Runtime.parse(value, DEPLOY.parent)
        record = self.release.state["slots"]["app_blue"]
        with self.assertRaisesRegex(
            cd.CDError, "configuration_requires_dedicated_release"
        ):
            self.operation.cd.guard(self.release, SHA, "b" * 40, record["image"])


if __name__ == "__main__":
    unittest.main()
