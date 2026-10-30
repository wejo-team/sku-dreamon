"""백업 대상 경계·실패 시 완료 표식 금지·비밀값 없는 오류를 검사한다."""

from __future__ import annotations

import contextlib
import copy
import fcntl
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import backup
from config import Runtime
from test_release import settings


class FakeCommands:
    """Docker·AWS 외부 경계를 대체하고 실제 파일·archive 검증은 유지한다."""

    def __init__(self, runtime: Runtime) -> None:
        self.calls: list[list[str]] = []
        self.container = {
            "Id": "a" * 64,
            "State": {"Running": True},
            "Config": {
                "Env": ["PGDATA=/var/lib/postgresql/data"],
                "Labels": {
                    "com.docker.compose.project": runtime.project,
                    "com.docker.compose.service": "postgres",
                },
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": str(runtime.data_dir),
                    "Destination": "/var/lib/postgresql/data",
                    "RW": True,
                }
            ],
        }
        self.ids = [self.container["Id"]]
        self.fail: str | None = None
        self.objects: dict[str, dict[str, object]] = {}
        self.archive_members: set[str] = set()
        self.archive_contents: dict[str, bytes] = {}

    def __call__(self, arguments: list[str], *, output=None, timeout=60):
        self.calls.append(arguments)
        if "pg_dump" in arguments:
            if self.fail == "dump":
                raise backup.BackupError("dump_failed")
            output.write(b"PGDMPsynthetic-archive")
            return b""
        if "inspect" in arguments:
            return json.dumps([self.container]).encode()
        if "ps" in arguments:
            return "\n".join(self.ids).encode()
        if "cp" in arguments:
            source, destination = arguments[3:5]
            if self.fail == Path(source).name:
                raise backup.BackupError("upload_failed")
            key = destination.split("/", 3)[3]
            self.objects[key] = {
                "ContentLength": Path(source).stat().st_size,
                "Metadata": {"sha256": backup.digest(Path(source))},
                "ServerSideEncryption": "aws:kms",
            }
            if Path(source).name == "runtime.tar.gz":
                with tarfile.open(source) as archive:
                    self.archive_members = set(archive.getnames())
                    self.archive_contents = {
                        member.name: archive.extractfile(member).read()
                        for member in archive.getmembers()
                        if member.isfile()
                    }
            return b""
        if "head-object" in arguments:
            result = dict(self.objects[arguments[arguments.index("--key") + 1]])
            if self.fail == "encryption":
                result["ServerSideEncryption"] = "AES256"
            return json.dumps(result).encode()
        return b""


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "runtime"
        self.root.mkdir(mode=0o700)
        self.runtime = Runtime.parse(settings(self.root), DEPLOY.parent)
        self.config = self.base / "runtime.json"
        self.config.write_text(json.dumps(settings(self.root)))
        self.config.chmod(0o600)
        for directory in (
            "private",
            "state",
            "state/certbot",
            "nginx",
            "acme/letsencrypt/archive/api.example.com",
            "acme/letsencrypt/live/api.example.com",
        ):
            (self.root / directory).mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in backup.REQUIRED_PRIVATE:
            (self.root / "private" / name).write_text("synthetic-secret")
            (self.root / "private" / name).chmod(0o600)
        (self.root / "private/compose.env").write_text("synthetic-compose")
        (self.root / "nginx/active.conf").write_text("synthetic-nginx")
        (
            self.root / "acme/letsencrypt/archive/api.example.com/fullchain1.pem"
        ).write_text("synthetic-certificate")
        (self.root / "acme/letsencrypt/live/api.example.com/fullchain.pem").symlink_to(
            "../../archive/api.example.com/fullchain1.pem"
        )
        self.state = {
            "version": 1,
            "phase": "stable",
            "postgres_id": "a" * 64,
            "host_identity": self.runtime.host_identity,
            "transaction": None,
            "active": "app_blue",
            "slots": {"app_blue": {"sha": "b" * 40}},
        }
        self.write_state()
        self.options = backup.Options("private-example-bucket", "ap-northeast-2")
        self.commands = FakeCommands(self.runtime)
        self.job = backup.Backup(
            self.runtime, self.config, DEPLOY.parent, self.options, self.commands
        )

    def write_state(self) -> None:
        path = self.root / "state/release.json"
        path.write_text(json.dumps(self.state))
        path.chmod(0o600)

    def test_success_requires_both_objects_and_preserves_acme_symlinks(self) -> None:
        self.job.run()
        names = [Path(key).name for key in self.commands.objects]
        self.assertEqual(names, ["database.dump", "runtime.tar.gz", "manifest.json"])
        self.assertTrue((self.root / "state/backup-last-success.json").exists())
        self.assertIn("runtime/private/db-ca.key", self.commands.archive_members)
        self.assertIn(
            "runtime/acme/letsencrypt/live/api.example.com/fullchain.pem",
            self.commands.archive_members,
        )
        self.assertNotIn("runtime/state/release.lock", self.commands.archive_members)

    def test_missing_or_multiple_database_refuses_backup(self) -> None:
        for ids in ([], ["a" * 64, "c" * 64]):
            with self.subTest(ids=ids):
                self.commands.ids = ids
                with self.assertRaises(backup.BackupError):
                    self.job.run()
                self.assertEqual(self.commands.objects, {})

    def test_wrong_label_or_mount_or_container_refuses_backup(self) -> None:
        original = copy.deepcopy(self.commands.container)
        cases = [
            lambda value: value["Config"]["Labels"].update(
                {"com.docker.compose.project": "another-project"}
            ),
            lambda value: value["Mounts"][0].update(Source="/unrelated/data"),
            lambda value: value["Mounts"][0].update(RW=False),
            lambda value: value.update(Id="c" * 64),
            lambda value: value["State"].update(Running=False),
        ]
        for mutation in cases:
            self.commands.container = copy.deepcopy(original)
            mutation(self.commands.container)
            with self.assertRaises(backup.BackupError):
                self.job.run()
            self.assertEqual(self.commands.objects, {})

    def test_dump_and_upload_failure_never_write_success(self) -> None:
        for failure in ("dump", "database.dump", "runtime.tar.gz", "manifest.json"):
            with self.subTest(failure=failure):
                self.commands.fail = failure
                self.commands.objects = {}
                with self.assertRaises(backup.BackupError):
                    self.job.run()
                self.assertFalse(
                    (self.root / "state/backup-last-success.json").exists()
                )
                self.assertFalse(
                    any(key.endswith("manifest.json") for key in self.commands.objects)
                )

    def test_failed_followup_preserves_previous_success(self) -> None:
        self.job.run()
        marker = self.root / "state/backup-last-success.json"
        previous = marker.read_bytes()
        self.commands.fail = "runtime.tar.gz"
        self.commands.objects = {}
        with self.assertRaises(backup.BackupError):
            self.job.run()
        self.assertEqual(marker.read_bytes(), previous)
        self.assertFalse(
            any(key.endswith("manifest.json") for key in self.commands.objects)
        )

    def test_wrong_remote_encryption_never_commits_success(self) -> None:
        self.commands.fail = "encryption"
        with self.assertRaisesRegex(backup.BackupError, "verification_failed"):
            self.job.run()
        self.assertFalse((self.root / "state/backup-last-success.json").exists())
        self.assertFalse(
            any(key.endswith("manifest.json") for key in self.commands.objects)
        )

    def test_active_release_lock_blocks_capture_without_external_commands(self) -> None:
        lock = self.root / "state/release.lock"
        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(backup.BackupError, "lock_unavailable"):
                self.job.run()
            self.assertEqual(self.commands.calls, [])
        finally:
            os.close(descriptor)

    def test_unstable_release_and_external_symlink_refuse_backup(self) -> None:
        self.state["phase"] = "draining"
        self.write_state()
        with self.assertRaises(backup.BackupError):
            self.job.run()
        self.state["phase"] = "stable"
        self.write_state()
        (self.root / "acme/letsencrypt/escape").symlink_to(self.config)
        with self.assertRaises(backup.BackupError):
            self.job.run()
        self.assertFalse(
            any(key.endswith("manifest.json") for key in self.commands.objects)
        )

    def test_archive_excludes_pgdata_logs_and_unlisted_private_files(self) -> None:
        for relative in (
            "private/unrelated.dump",
            "acme/logs/raw.log",
            "postgres/pgdata/secret",
            "state/unsafe.env",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("must-not-be-archived")
        self.job.run()
        for relative in (
            "private/unrelated.dump",
            "acme/logs/raw.log",
            "postgres/pgdata/secret",
            "state/unsafe.env",
        ):
            self.assertNotIn("runtime/" + relative, self.commands.archive_members)

    def test_openai_key_is_redacted_only_in_archive_and_db_secrets_are_preserved(
        self,
    ) -> None:
        secret = "synthetic-openai-key-must-not-survive"
        value = json.loads(self.config.read_text())
        value["app_env"]["OPENAI_API_KEY"] = secret
        self.config.write_text(json.dumps(value))
        environment = self.root / "private" / ("app-" + "a" * 64 + ".env")
        original = f"OPENAI_API_KEY={secret}\nDATABASE_URL=synthetic-database-secret\n"
        environment.write_text(original)
        self.job.run()
        self.assertTrue(self.job.openai_key_redacted)
        for content in self.commands.archive_contents.values():
            self.assertNotIn(secret.encode(), content)
        archived_env = self.commands.archive_contents[
            "runtime/private/" + environment.name
        ]
        self.assertIn(backup.OPENAI_KEY_SENTINEL.encode(), archived_env)
        self.assertIn(b"DATABASE_URL=synthetic-database-secret", archived_env)
        self.assertEqual(environment.read_text(), original)
        self.assertEqual(
            json.loads(self.config.read_text())["app_env"]["OPENAI_API_KEY"], secret
        )
        self.assertIn(
            b"synthetic-secret",
            self.commands.archive_contents["runtime/private/db-ca.key"],
        )

    def test_subprocess_error_hides_command_output_and_secrets(self) -> None:
        import subprocess

        with (
            patch(
                "backup.subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    1, ["secret-command"], stderr=b"secret-password"
                ),
            ),
            self.assertRaises(backup.BackupError) as error,
        ):
            backup.command(["synthetic-program", "secret-argument"])
        self.assertEqual(str(error.exception), "command_failed")

    def test_failure_notification_contains_only_fixed_metadata(self) -> None:
        self.options = backup.Options(
            "private-example-bucket",
            "ap-northeast-2",
            "arn:aws:sns:ap-northeast-2:123456789012:operations",
        )
        backup.notify_failure(self.options, "runtime_invalid", self.commands)
        call = self.commands.calls[-1]
        message = json.loads(call[call.index("--message") + 1])
        self.assertEqual(set(message), {"event", "code", "time"})
        self.assertEqual(message["code"], "runtime_invalid")

    def test_cli_error_is_sanitized(self) -> None:
        output = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {
                    "BACKUP_BUCKET": "private-example-bucket",
                    "BACKUP_REGION": "ap-northeast-2",
                },
                clear=True,
            ),
            patch("backup.os.geteuid", return_value=0),
            patch(
                "backup.Runtime.read",
                side_effect=ValueError("sensitive-runtime-content"),
            ),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(backup.main(["--config", str(self.config)]), 1)
        self.assertNotIn("sensitive", output.getvalue())
        self.assertIn("backup_failed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
