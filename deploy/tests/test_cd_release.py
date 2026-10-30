"""CD 경계와 기존 release 엔진의 실제 실패·복구 조합을 검사한다."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import py_compile
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import cd_release as cd
from config import ReleaseError, Runtime, atomic_write
from test_release import NEW_SHA, SHA, FakeRelease, settings

REPOSITORY = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/synthetic-app"
DIGEST = "2" * 64
OLD_IMAGE = REPOSITORY + "@sha256:" + "1" * 64
IMAGE = REPOSITORY + "@sha256:" + DIGEST


def archive_bytes(extra: list[tarfile.TarInfo] | None = None) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name in (
            "deploy/release.py",
            "deploy/config.py",
            "deploy/compose.production.yaml",
        ):
            member = tarfile.TarInfo(name)
            member.size = 8
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(b"fixture\n"))
        for member in extra or []:
            archive.addfile(
                member, io.BytesIO(b"x" * member.size) if member.isfile() else None
            )
    return output.getvalue()


class Engine(FakeRelease):
    """배포 상태기는 실제 코드이며 Docker·migration job만 대체한다."""

    def migrate(self, transaction):
        self.events.append("migration")
        transaction["migration"]["status"] = "complete"
        self.save()

    def migration_container(self, migration):
        return {"Id": "migration-fixture", "State": {"Running": False, "ExitCode": 0}}


class Commands:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.archive = archive_bytes()
        self.calls: list[list[str]] = []
        self.password = b"synthetic-credential-never-log"
        self.on_backup = None
        self.fail_backup = False
        self.stale_backup = False
        self.wrong_label = False
        self.wrong_digest = False
        self.backups = 0
        self.config_paths: list[Path] = []

    def __call__(self, arguments, *, data=None, timeout=60):
        self.calls.append(arguments)
        if arguments[:3] == ["aws", "s3", "cp"]:
            Path(arguments[4]).write_bytes(self.archive)
            return b""
        if arguments[:3] == ["aws", "ecr", "get-login-password"]:
            return self.password
        if arguments[0] == "docker":
            self.config_paths.append(Path(arguments[4]))
            if "login" in arguments:
                if data != self.password:
                    raise AssertionError("password must use stdin")
                return b"private login output"
            if "inspect" in arguments:
                image = arguments[-1]
                sha = SHA if image == OLD_IMAGE else NEW_SHA
                return json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {
                                    "org.opencontainers.image.revision": SHA
                                    if self.wrong_label
                                    else sha
                                }
                            },
                            "RepoDigests": [] if self.wrong_digest else [image],
                        }
                    ]
                ).encode()
            return b"private pull output"
        if arguments[:2] == ["systemctl", "start"]:
            if self.fail_backup:
                raise cd.CDError("host_operation_failed")
            if not self.stale_backup:
                self.backups += 1
                state = self.engine.state
                marker = {
                    "status": "complete",
                    "backup_id": f"backup-{self.backups}",
                    "release_sha": state["slots"][state["active"]]["sha"],
                    "objects": [{}, {}],
                }
                atomic_write(
                    self.engine.root / "state" / "backup-last-success.json",
                    json.dumps(marker),
                )
            if self.on_backup:
                self.on_backup()
            return b""
        raise AssertionError("unexpected external operation")


class CDTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        root = self.base / "runtime"
        value = settings(root)
        self.release = Engine(Runtime.parse(value, DEPLOY.parent))
        root.chmod(0o700)
        self.release.worker_plan = [["10:100"], []]
        self.release.state["slots"]["app_blue"]["image"] = OLD_IMAGE
        self.release.save()
        self.config_path = self.base / "runtime.json"
        atomic_write(self.config_path, json.dumps(value))
        self.releases = self.base / "releases"
        self.releases.mkdir()
        (self.releases / SHA).mkdir()
        self.current = self.base / "current"
        self.current.symlink_to(self.releases / SHA)
        self.config = cd.Config(
            "ap-northeast-2",
            "synthetic-artifacts",
            REPOSITORY,
            self.config_path,
            self.releases,
            self.current,
        )
        self.commands = Commands(self.release)
        self.source_hash = hashlib.sha256(self.commands.archive).hexdigest()

        @contextlib.contextmanager
        def factory(config, checkout):
            self.release.checkout = checkout
            yield self.release

        self.factory = factory
        # 기존 엔진은 root 전용이다. 테스트에서는 같은 사용자·0600 검사를 유지한다.
        self.addCleanup(patch.stopall)
        patch(
            "config.private_path",
            side_effect=lambda path, **kw: cd.trusted(path, private=True, **kw),
        ).start()
        self.cd = cd.CDRelease(
            self.config, runner=self.commands, engine_factory=factory
        )

    def deploy(self):
        return self.cd.change("deploy", NEW_SHA, SHA, self.source_hash, DIGEST)

    def test_success_backup_precedes_migration_and_publishes_current(self):
        result = self.deploy()
        self.assertEqual(result, {"deployed_sha": NEW_SHA, "previous_sha": SHA})
        self.assertEqual(self.current.resolve(), self.releases / NEW_SHA)
        self.assertEqual(self.release.state["postgres_id"], "database-original")
        self.assertEqual(self.release.events.count("migration"), 1)
        self.assertEqual(self.commands.backups, 1)
        self.assertTrue(all(not path.exists() for path in self.commands.config_paths))
        self.assertNotIn(self.commands.password.decode(), str(self.commands.calls))
        self.assertFalse(
            any("down" in args or "volume" in args for args in self.commands.calls)
        )

    def test_same_release_retry_is_noop_and_cache_tampering_is_rejected(self):
        self.deploy()
        self.deploy()
        self.assertEqual(self.commands.backups, 1)
        self.assertEqual(self.release.events.count("migration"), 1)
        (self.releases / NEW_SHA / "deploy" / "release.py").write_text("tampered")
        with self.assertRaisesRegex(cd.CDError, "cached_source_mismatch"):
            self.deploy()
        self.assertEqual(self.current.resolve().name, NEW_SHA)

    def test_finished_journal_with_old_link_is_reconciled_without_second_migration(
        self,
    ):
        self.deploy()
        self.current.unlink()
        self.current.symlink_to(self.releases / SHA)
        self.deploy()
        self.assertEqual(self.current.resolve().name, NEW_SHA)
        self.assertEqual(self.release.events.count("migration"), 1)

    def test_stale_current_is_rejected_before_any_external_call(self):
        with self.assertRaisesRegex(cd.CDError, "current_release_changed"):
            self.cd.change("deploy", NEW_SHA, "c" * 40, self.source_hash, DIGEST)
        self.assertEqual(self.commands.calls, [])

    def test_normal_root_owned_python_cache_does_not_change_source_identity(self):
        self.deploy()
        cached = self.releases / NEW_SHA / "deploy" / "__pycache__"
        cached.mkdir()
        (cached / "config.cpython-313.pyc").write_bytes(b"generated cache")
        self.deploy()
        self.assertEqual(self.release.events.count("migration"), 1)
        (cached / "untracked.txt").write_text("unexpected")
        with self.assertRaisesRegex(cd.CDError, "unexpected_python_cache"):
            self.deploy()

    def test_release_change_during_backup_is_not_overwritten(self):
        def race():
            self.release.state["slots"]["app_blue"]["sha"] = "c" * 40
            self.release.save()

        self.commands.on_backup = race
        with self.assertRaisesRegex(cd.CDError, "current_release_changed"):
            self.deploy()
        self.assertNotIn("migration", self.release.events)
        self.assertEqual(self.release.state["slots"]["app_blue"]["sha"], "c" * 40)

    def test_cd_and_release_lock_conflicts_preserve_running_app(self):
        with self.cd.lock(), self.assertRaisesRegex(cd.CDError, "cd_busy"):
            self.deploy()
        with self.release.lock(), self.assertRaises(ReleaseError):
            self.deploy()
        self.assertEqual(self.commands.calls, [])
        self.assertEqual(self.current.resolve().name, SHA)

    def test_failed_or_stale_backup_never_starts_migration(self):
        for flag in ("fail_backup", "stale_backup"):
            with self.subTest(flag=flag):
                setattr(self.commands, flag, True)
                with self.assertRaises((cd.CDError, FileNotFoundError)):
                    self.deploy()
                setattr(self.commands, flag, False)
                self.assertNotIn("migration", self.release.events)
                self.assertEqual(self.current.resolve().name, SHA)

    def test_source_hash_or_image_identity_mismatch_never_backs_up_or_deploys(self):
        with self.assertRaisesRegex(cd.CDError, "source_hash_mismatch"):
            self.cd.change("deploy", NEW_SHA, SHA, "f" * 64, DIGEST)
        self.assertFalse((self.releases / NEW_SHA).exists())
        for flag in ("wrong_label", "wrong_digest"):
            with self.subTest(flag=flag):
                setattr(self.commands, flag, True)
                with self.assertRaisesRegex(cd.CDError, "image_identity_mismatch"):
                    self.deploy()
                setattr(self.commands, flag, False)
        self.assertEqual(self.commands.backups, 0)
        self.assertNotIn("migration", self.release.events)

    def test_readiness_failure_recovers_old_release_and_preserves_database(self):
        self.release.fail_ready = "app_green"
        with self.assertRaisesRegex(cd.CDError, "release_failed_restored"):
            self.deploy()
        self.assertEqual(self.release.state["phase"], "stable")
        self.assertIsNone(self.release.state["transaction"])
        self.assertEqual(self.current.resolve().name, SHA)
        self.assertTrue(self.release.actual["app_blue"]["State"]["Running"])
        self.assertTrue(self.release.actual["postgres"]["State"]["Running"])

    def test_uncertain_reload_keeps_failed_journal_for_manual_recovery(self):
        self.release.fail_reload = True
        with self.assertRaisesRegex(cd.CDError, "recovery_required"):
            self.deploy()
        self.assertIsNotNone(self.release.state["transaction"])
        self.assertEqual(self.current.resolve().name, SHA)

    def test_link_failure_after_cutover_rolls_back_with_existing_engine(self):
        original = self.cd.publish
        attempts = 0

        def fail_once(sha, *, allowed):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("synthetic link failure")
            return original(sha, allowed=allowed)

        with (
            patch.object(self.cd, "publish", side_effect=fail_once),
            self.assertRaisesRegex(cd.CDError, "release_failed_restored"),
        ):
            self.deploy()
        self.assertEqual(
            self.release.state["slots"][self.release.state["active"]]["sha"], SHA
        )
        self.assertEqual(self.current.resolve().name, SHA)
        self.assertEqual(self.release.events.count("migration"), 1)

    def test_rollback_only_accepts_previous_and_does_not_migrate(self):
        self.deploy()
        before = len(self.commands.calls)
        with self.assertRaisesRegex(cd.CDError, "rollback_target_changed"):
            self.cd.change("rollback", "c" * 40, NEW_SHA)
        self.assertEqual(len(self.commands.calls), before)
        result = self.cd.change("rollback", SHA, NEW_SHA)
        self.assertEqual(result, {"deployed_sha": SHA, "previous_sha": NEW_SHA})
        self.assertEqual(self.current.resolve().name, SHA)
        self.assertEqual(self.release.events.count("migration"), 1)

    def test_status_exposes_only_contract_metadata(self):
        self.release.state["slots"]["app_blue"]["env_secret"] = "synthetic-do-not-log"
        self.release.save()
        result = self.cd.status()
        self.assertEqual(
            set(result), {"phase", "active_sha", "previous_sha", "active_image"}
        )
        self.assertNotIn("synthetic-do-not-log", json.dumps(result))


class ArchiveTests(unittest.TestCase):
    def test_engine_uses_verified_source_even_when_matching_stale_bytecode_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deploy").mkdir()
            source = root / "deploy" / "config.py"
            body = "class Runtime:\n @staticmethod\n def read(*args): return 'stale'\n"
            source.write_text(body)
            timestamp = source.stat().st_mtime_ns
            py_compile.compile(str(source), doraise=True)
            source.write_text(body.replace("stale", "fresh"))
            os.utime(source, ns=(timestamp, timestamp))
            (root / "deploy" / "release.py").write_text(
                "class Release:\n def __init__(self, runtime, checkout): self.runtime = runtime\n"
            )
            config = cd.Config(
                "ap-northeast-2",
                "synthetic-artifacts",
                REPOSITORY,
                root / "unused.json",
                root,
                root / "current",
            )
            previous = sys.modules.get("config")
            with cd.engine(config, root) as release:
                self.assertEqual(release.runtime, "fresh")
            self.assertIs(sys.modules.get("config"), previous)

    def test_rejects_traversal_links_devices_duplicates_and_reserved_marker(self):
        entries = []
        for name in (
            "../escaped",
            "/absolute",
            "deploy/../../escape",
            "deploy/./x",
            "deploy//x",
            "deploy\\x",
            cd.MARKER,
            "deploy/release.py",
            "deploy/__pycache__/config.cpython-313.pyc",
            "deploy/config.pyc",
        ):
            entries.append(tarfile.TarInfo(name))
        for kind in (
            tarfile.SYMTYPE,
            tarfile.LNKTYPE,
            tarfile.FIFOTYPE,
            tarfile.CHRTYPE,
        ):
            item = tarfile.TarInfo("deploy/untrusted")
            item.type = kind
            item.linkname = "../../escape"
            entries.append(item)
        for item in entries:
            with (
                self.subTest(name=item.name, type=item.type),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                archive = root / "source.tar.gz"
                archive.write_bytes(archive_bytes([item]))
                destination = root / "checkout"
                destination.mkdir()
                with self.assertRaises(cd.CDError):
                    cd.extract(archive, destination)
                self.assertFalse((root / "escaped").exists())

    def test_expansion_limit_is_enforced_before_extracting_large_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "source.tar.gz"
            archive.write_bytes(archive_bytes())
            destination = root / "checkout"
            destination.mkdir()
            with (
                patch.object(cd, "MAX_BYTES", 7),
                self.assertRaisesRegex(cd.CDError, "source_limit_exceeded"),
            ):
                cd.extract(archive, destination)

    def test_subprocess_and_main_errors_never_echo_secrets(self):
        secret = "fixture-secret-value"
        with (
            patch.object(
                subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, [secret], stderr=secret),
            ),
            self.assertRaisesRegex(cd.CDError, "host_operation_failed") as caught,
        ):
            cd.run(["tool", secret])
        self.assertNotIn(secret, str(caught.exception))
        output = io.StringIO()
        with (
            patch.object(
                sys, "argv", ["cd_release", "--config", "/unused", "--action", "status"]
            ),
            patch.object(os, "geteuid", return_value=0),
            patch.object(cd.Config, "read", side_effect=ValueError(secret)),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(cd.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {"error": "cd_failed"})


if __name__ == "__main__":
    unittest.main()
