"""상위 CD의 검사 게이트·복구 분기·SSM 인자를 외부 호출 없이 검증한다."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import cd  # noqa: E402
import cd_frontend  # noqa: E402

SHA = "b" * 40
OLD_SHA = "a" * 40
DIGEST = "c" * 64
SOURCE = "d" * 64
SITE = "https://app.example.invalid"
API = "https://api.example.invalid/api/v1"
ENVIRONMENT = {
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_SHA": SHA,
    "GITHUB_REPOSITORY": "synthetic/project",
    "GITHUB_RUN_ID": "123",
    "GITHUB_RUN_ATTEMPT": "2",
    "ARTIFACT_BUCKET": "synthetic-artifacts",
    "FRONTEND_BUCKET": "synthetic-frontend",
    "CLOUDFRONT_DISTRIBUTION_ID": "DISTRIBUTION1",
    "SITE_URL": SITE,
    "API_BASE_URL": API,
    "AWS_REGION": "ap-northeast-2",
    "DEPLOY_INSTANCE_ID": "i-synthetic",
    "DEPLOY_SSM_DOCUMENT": "synthetic-release",
}


def checks() -> list[dict]:
    return [
        {
            "id": index,
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "app": {"slug": "github-actions"},
        }
        for index, name in enumerate(("Frontend", "Backend", "Validate docs"), 1)
    ]


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, ENVIRONMENT, clear=True).start()
        self.run = patch.object(cd, "run", return_value=(SHA + "\n").encode()).start()

    def test_exact_main_push_and_checkout_are_required(self) -> None:
        cd.validate_context(SHA)
        for change in (
            {"GITHUB_EVENT_NAME": "pull_request"},
            {"GITHUB_EVENT_NAME": "workflow_dispatch"},
            {"GITHUB_REF": "refs/heads/develop"},
            {"GITHUB_REF": "refs/tags/main"},
            {"GITHUB_SHA": OLD_SHA},
        ):
            with self.subTest(change=change), patch.dict(os.environ, change):
                with self.assertRaises(cd.DeploymentError):
                    cd.validate_context(SHA)
        self.run.return_value = (OLD_SHA + "\n").encode()
        with self.assertRaises(cd.DeploymentError):
            cd.validate_context(SHA)
        for malformed in ("main", SHA[:12], SHA.upper(), "b" * 41):
            with self.subTest(sha=malformed), self.assertRaises(cd.DeploymentError):
                cd.validate_context(malformed)

    def test_latest_failed_check_cannot_use_an_older_success(self) -> None:
        for name in ("Frontend", "Backend", "Validate docs"):
            data = checks()
            data.append(
                {
                    "id": 99,
                    "name": name,
                    "status": "completed",
                    "conclusion": "failure",
                    "app": {"slug": "github-actions"},
                }
            )
            with self.subTest(name=name), self.assertRaises(cd.DeploymentError):
                cd.successful_checks(data)
            data.reverse()
            with (
                self.subTest(name=name, order="reversed"),
                self.assertRaises(cd.DeploymentError),
            ):
                cd.successful_checks(data)

    def test_new_success_supersedes_failure_but_running_retry_waits(self) -> None:
        data = checks()
        data[0]["conclusion"] = "failure"
        latest = {
            "id": 20,
            "name": "Frontend",
            "status": "completed",
            "conclusion": "success",
            "app": {"slug": "github-actions"},
        }
        data.append(latest)
        self.assertTrue(cd.successful_checks(data))
        latest["status"] = "in_progress"
        latest["conclusion"] = None
        self.assertFalse(cd.successful_checks(data))

    def test_checks_from_another_app_neither_satisfy_nor_override_actions(self) -> None:
        data = checks()
        data[0]["app"] = {"slug": "untrusted-app"}
        self.assertFalse(cd.successful_checks(data))
        data = checks()
        data.append(
            {
                "id": 1000,
                "name": "Backend",
                "status": "completed",
                "conclusion": "failure",
                "app": {"slug": "untrusted-app"},
            }
        )
        self.assertTrue(cd.successful_checks(data))
        self.assertFalse(cd.successful_checks([]))

    def test_gate_requests_only_the_exact_commit_checks(self) -> None:
        paths = []

        def github(path):
            paths.append(path)
            if path.endswith("/commits/main"):
                return {"sha": SHA}
            self.assertEqual(
                path, f"repos/synthetic/project/commits/{SHA}/check-runs?per_page=100"
            )
            return {"check_runs": checks()}

        with patch.object(cd, "gh", side_effect=github):
            self.assertTrue(cd.gate(SHA))
        self.assertEqual(len(paths), 2)

    def test_gate_skips_superseded_main_without_reading_checks(self) -> None:
        with patch.object(cd, "gh", return_value={"sha": OLD_SHA}) as github:
            self.assertFalse(cd.gate(SHA))
        self.assertEqual(github.call_count, 1)

    def test_gate_timeout_does_not_accept_missing_checks(self) -> None:
        with (
            patch.object(cd, "latest_main", return_value=True),
            patch.object(cd, "gh", return_value={"check_runs": []}),
            patch.object(cd.time, "monotonic", side_effect=[0, 0, 901]),
            patch.object(cd.time, "sleep"),
        ):
            with self.assertRaisesRegex(cd.DeploymentError, "deadline"):
                cd.gate(SHA)


class DeployTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.addCleanup(patch.stopall)
        patch.dict(
            os.environ, {**ENVIRONMENT, "RUNNER_TEMP": str(self.root)}, clear=True
        ).start()
        self.events = []
        self.uploads = {}
        self.active = OLD_SHA
        self.frontend_failure = None
        self.api_failure = None
        self.fail_recovery_upload = False
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.latest = patch.object(cd, "latest_main", return_value=True).start()
        self.command = patch.object(cd, "run", side_effect=self.run_command).start()
        self.build_image = patch.object(cd, "image", side_effect=self.image).start()
        self.aws = patch.object(cd, "aws", side_effect=self.upload).start()
        self.host = patch.object(cd, "host", side_effect=self.host_action).start()
        self.verify = patch.object(cd, "verify_api", side_effect=self.api).start()
        self.publish = patch.object(
            cd_frontend, "publish", side_effect=self.frontend
        ).start()

    def run_command(self, *args, **kwargs):
        if args == ("git", "rev-parse", "HEAD"):
            return (SHA + "\n").encode()
        if args[:2] == ("git", "archive"):
            destination = Path(
                next(
                    arg.removeprefix("--output=")
                    for arg in args
                    if arg.startswith("--output=")
                )
            )
            self.assertEqual(args[-1], SHA)
            with tarfile.open(destination, "w:gz") as archive:
                content = b"synthetic release source\n"
                member = tarfile.TarInfo("backend/app/main.py")
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            self.events.append("archive")
            return b""
        raise AssertionError(f"unexpected command boundary: {args[:2]}")

    def image(self, sha, state_dir):
        self.assertEqual(sha, SHA)
        self.assertTrue(state_dir.is_dir())
        self.events.append("image")
        return DIGEST

    def upload(self, *args):
        self.assertEqual(args[:2], ("s3api", "put-object"))
        key = args[args.index("--key") + 1]
        content = Path(args[args.index("--body") + 1]).read_bytes()
        if "/recovery/" in key and self.fail_recovery_upload:
            raise cd.DeploymentError("private upload diagnostic must not be printed")
        self.uploads[key] = content
        self.events.append(
            "recovery-upload" if "/recovery/" in key else "source-upload"
        )
        return {}

    def host_action(self, action, **kwargs):
        self.events.append((action, kwargs))
        if action == "status":
            return {"phase": "stable", "active_sha": self.active}
        if action == "deploy":
            self.assertEqual(kwargs["expected"], self.active)
            self.active = kwargs["sha"]
            return {"status": "deployed"}
        if action == "rollback":
            self.assertEqual(kwargs, {"sha": OLD_SHA, "expected": SHA})
            self.assertEqual(self.active, SHA)
            self.active = OLD_SHA
            return {"status": "rolled_back"}
        raise AssertionError(action)

    def api(self, sha):
        self.events.append(("verify", sha))
        self.assertEqual(self.active, sha)
        if sha == self.api_failure:
            raise cd.DeploymentError("synthetic public API verification failed")

    def frontend(self, **kwargs):
        self.events.append("frontend")
        self.assertEqual(kwargs["sha"], SHA)
        self.assertEqual(kwargs["api_base_url"], API)
        self.assertEqual(kwargs["site_url"], SITE)
        state = kwargs["state_dir"]
        state.mkdir()
        (state / "snapshot.json").write_text('{"private": "do-not-log-snapshot"}')
        (state / "receipt.json").write_text('{"status": "synthetic"}')
        if self.frontend_failure is not None:
            raise cd_frontend.PublicationError(
                "synthetic publication failure",
                rollback_succeeded=self.frontend_failure,
            )
        return {"release_sha": SHA, "invalidation_id": "SYNTHETIC"}

    def local_frontend(self) -> Path:
        return next(self.root.glob("dreamon-cd-*/frontend"))

    def test_success_uses_archive_digest_and_verifies_api_before_frontend(self) -> None:
        result = cd.deploy(SHA)
        self.assertEqual(result["status"], "deployed")
        self.assertEqual(self.active, SHA)
        source_key = f"artifacts/cd/{SHA}/source.tar.gz"
        source_hash = hashlib.sha256(self.uploads[source_key]).hexdigest()
        deploy_call = self.host.call_args_list[1]
        self.assertEqual(deploy_call.args, ("deploy",))
        self.assertEqual(
            deploy_call.kwargs,
            {"sha": SHA, "source": source_hash, "digest": DIGEST, "expected": OLD_SHA},
        )
        self.assertLess(
            self.events.index(("verify", SHA)), self.events.index("frontend")
        )
        self.assertFalse(
            any(call.args == ("rollback",) for call in self.host.call_args_list)
        )

    def test_initial_superseded_main_skips_before_any_mutation(self) -> None:
        self.latest.return_value = False
        result = cd.deploy(SHA)
        self.assertEqual(result, {"status": "skipped", "reason": "superseded_main"})
        self.build_image.assert_not_called()
        self.aws.assert_not_called()
        self.host.assert_not_called()
        self.publish.assert_not_called()

    def test_main_changed_during_image_preparation_skips_production_mutation(
        self,
    ) -> None:
        self.latest.side_effect = [True, False]
        result = cd.deploy(SHA)
        self.assertEqual(result["status"], "skipped")
        self.build_image.assert_called_once()
        self.aws.assert_not_called()
        self.host.assert_not_called()
        self.publish.assert_not_called()

    def test_restored_frontend_rolls_backend_back_with_guard_then_checks_old_api(
        self,
    ) -> None:
        self.frontend_failure = True
        with self.assertRaisesRegex(cd.DeploymentError, "previous release restored"):
            cd.deploy(SHA)
        self.assertEqual(self.active, OLD_SHA)
        self.assertEqual(self.host.call_args_list[-1].args, ("rollback",))
        self.assertEqual(
            self.host.call_args_list[-1].kwargs, {"sha": OLD_SHA, "expected": SHA}
        )
        self.assertEqual(self.verify.call_args_list[-1].args, (OLD_SHA,))
        self.assertTrue((self.local_frontend() / "snapshot.json").exists())
        recovery_key = f"artifacts/cd/{SHA}/recovery/123-2.tar.gz"
        with tarfile.open(
            fileobj=io.BytesIO(self.uploads[recovery_key]), mode="r:gz"
        ) as archive:
            self.assertIn("frontend/snapshot.json", archive.getnames())
        self.assertNotIn("do-not-log-snapshot", self.output.getvalue())

    def test_incomplete_frontend_restore_keeps_new_backend_and_recovery_files(
        self,
    ) -> None:
        self.frontend_failure = False
        with self.assertRaisesRegex(cd.DeploymentError, "frontend restore incomplete"):
            cd.deploy(SHA)
        self.assertEqual(self.active, SHA)
        self.assertFalse(
            any(call.args == ("rollback",) for call in self.host.call_args_list)
        )
        self.assertEqual(self.verify.call_count, 1)
        self.assertTrue((self.local_frontend() / "receipt.json").exists())
        self.assertTrue(any("/recovery/" in key for key in self.uploads))

    def test_api_failure_rolls_backend_back_without_publishing_frontend(self) -> None:
        self.api_failure = SHA
        with self.assertRaises(cd.DeploymentError):
            cd.deploy(SHA)
        self.publish.assert_not_called()
        self.assertEqual(self.active, OLD_SHA)
        self.assertEqual(
            [call.args[0] for call in self.verify.call_args_list], [SHA, OLD_SHA]
        )
        self.assertEqual(
            self.host.call_args_list[-1].kwargs, {"sha": OLD_SHA, "expected": SHA}
        )

    def test_failed_old_api_verification_is_not_reported_as_restored(self) -> None:
        self.frontend_failure = True
        self.api_failure = OLD_SHA
        with self.assertRaisesRegex(
            cd.DeploymentError, "synthetic public API verification failed"
        ):
            cd.deploy(SHA)
        self.assertNotIn('"status": "rolled_back"', self.output.getvalue())

    def test_recovery_upload_failure_cannot_prevent_backend_rollback(self) -> None:
        self.frontend_failure = True
        self.fail_recovery_upload = True
        with self.assertRaises(cd.DeploymentError):
            cd.deploy(SHA)
        self.assertEqual(self.active, OLD_SHA)
        self.assertEqual(self.verify.call_args_list[-1].args, (OLD_SHA,))
        self.assertTrue((self.local_frontend() / "snapshot.json").exists())
        self.assertIn('"local_state_preserved": true', self.output.getvalue())
        self.assertNotIn("private upload diagnostic", self.output.getvalue())

    def test_same_release_failure_does_not_roll_back_to_itself(self) -> None:
        self.active = SHA
        self.frontend_failure = True
        with self.assertRaises(cd.DeploymentError):
            cd.deploy(SHA)
        self.assertEqual(self.active, SHA)
        self.assertFalse(
            any(call.args == ("rollback",) for call in self.host.call_args_list)
        )
        self.assertEqual(self.verify.call_count, 1)

    def test_incomplete_restore_and_evidence_upload_failure_keep_local_recovery(
        self,
    ) -> None:
        self.frontend_failure = False
        self.fail_recovery_upload = True
        with self.assertRaisesRegex(cd.DeploymentError, "frontend restore incomplete"):
            cd.deploy(SHA)
        self.assertEqual(self.active, SHA)
        self.assertFalse(
            any(call.args == ("rollback",) for call in self.host.call_args_list)
        )
        self.assertTrue((self.local_frontend() / "snapshot.json").exists())

    def test_recovery_tar_failure_cannot_prevent_backend_rollback(self) -> None:
        self.frontend_failure = True
        original_open = tarfile.open

        def archive(path=None, *args, **kwargs):
            if path and Path(path).name == "frontend-recovery.tar.gz":
                raise OSError("synthetic archive failure")
            return original_open(path, *args, **kwargs)

        with patch.object(cd.tarfile, "open", side_effect=archive):
            with self.assertRaises(cd.DeploymentError):
                cd.deploy(SHA)
        self.assertEqual(self.active, OLD_SHA)
        self.assertEqual(self.verify.call_args_list[-1].args, (OLD_SHA,))
        self.assertTrue((self.local_frontend() / "snapshot.json").exists())


class RecoveryTests(unittest.TestCase):
    def test_path_inspection_failure_is_best_effort(self) -> None:
        with (
            patch.object(
                Path, "exists", side_effect=OSError("synthetic permission error")
            ),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            cd.preserve_recovery(Path("/synthetic-state"), SHA)
        self.assertIn('"recovery_upload": "failed"', output.getvalue())


class ApiVerificationTests(unittest.TestCase):
    def response(self, **changes):
        response = io.BytesIO(b'{"status":"ok"}')
        response.status = 200
        response.url = API + "/health"
        response.headers = {
            "X-Release-ID": SHA,
            "Access-Control-Allow-Origin": SITE,
            "Access-Control-Allow-Credentials": "true",
        }
        for name, value in changes.items():
            setattr(response, name, value)
        return response

    def test_exact_release_and_credentialed_origin_are_verified(self) -> None:
        with (
            patch.dict(os.environ, ENVIRONMENT, clear=True),
            patch.object(cd, "urlopen", return_value=self.response()) as request,
        ):
            cd.verify_api(SHA)
        self.assertEqual(request.call_args.args[0].full_url, API + "/health")
        self.assertEqual(request.call_args.args[0].get_header("Origin"), SITE)
        self.assertEqual(request.call_args.kwargs["timeout"], 20)

    def test_wrong_release_cors_redirect_status_or_body_are_rejected(self) -> None:
        for header, value in (
            ("X-Release-ID", OLD_SHA),
            ("Access-Control-Allow-Origin", "https://other.example.invalid"),
            ("Access-Control-Allow-Credentials", "false"),
        ):
            response = self.response()
            response.headers[header] = value
            with (
                self.subTest(header=header),
                patch.dict(os.environ, ENVIRONMENT, clear=True),
                patch.object(cd, "urlopen", return_value=response),
                self.assertRaises(cd.DeploymentError),
            ):
                cd.verify_api(SHA)
        for change in ({"status": 503}, {"url": SITE + "/health"}):
            with (
                self.subTest(change=change),
                patch.dict(os.environ, ENVIRONMENT, clear=True),
                patch.object(cd, "urlopen", return_value=self.response(**change)),
                self.assertRaises(cd.DeploymentError),
            ):
                cd.verify_api(SHA)
        response = self.response()
        response.seek(0)
        response.truncate()
        response.write(b'{"status":"not-ok"}')
        response.seek(0)
        with (
            patch.dict(os.environ, ENVIRONMENT, clear=True),
            patch.object(cd, "urlopen", return_value=response),
            self.assertRaises(cd.DeploymentError),
        ):
            cd.verify_api(SHA)


class HostPollingTests(unittest.TestCase):
    def test_timed_out_poll_is_bounded_by_remaining_deadline_and_reports_unknown(
        self,
    ) -> None:
        with (
            patch.dict(os.environ, ENVIRONMENT, clear=True),
            patch.object(
                cd, "aws", return_value={"Command": {"CommandId": "SYNTHETIC"}}
            ),
            patch.object(cd.time, "monotonic", side_effect=[0] + [1845] * 10),
            patch.object(
                cd.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("private command", 5),
            ) as invocation,
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(cd.DeploymentError, "outcome unknown") as raised,
        ):
            cd.host("status")
        self.assertGreater(invocation.call_args.kwargs["timeout"], 0)
        self.assertLessEqual(invocation.call_args.kwargs["timeout"], 5)
        self.assertNotIn("private command", str(raised.exception))

    def test_failed_remote_status_cannot_return_success_payload_or_leak_output(
        self,
    ) -> None:
        completed = subprocess.CompletedProcess(
            ["aws"],
            0,
            stdout=json.dumps(
                {"Status": "Failed", "StandardOutputContent": "private remote output"}
            ).encode(),
            stderr=b"",
        )
        with (
            patch.dict(os.environ, ENVIRONMENT, clear=True),
            patch.object(
                cd, "aws", return_value={"Command": {"CommandId": "SYNTHETIC"}}
            ),
            patch.object(cd.subprocess, "run", return_value=completed),
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaises(cd.DeploymentError) as raised,
        ):
            cd.host("status")
        self.assertNotIn(
            "private remote output", str(raised.exception) + output.getvalue()
        )


class SSMDocumentTests(unittest.TestCase):
    def test_real_shell_routes_only_action_specific_arguments_to_fake_receiver(
        self,
    ) -> None:
        document = json.loads((DEPLOY / "ssm-production-release.json").read_text())
        commands = document["mainSteps"][0]["inputs"]["runCommand"]
        self.assertTrue(
            all(
                parameter["interpolationType"] == "ENV_VAR"
                for parameter in document["parameters"].values()
            )
        )
        original_shell = "\n".join(commands)
        self.assertNotIn("{{", original_shell)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / "current-runner.py"
            fallback = root / "fallback-runner.py"
            fallback.write_text(
                'raise AssertionError("must never execute production runner")\n'
            )
            receiver = root / "fake-python"
            receiver.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                'Path(os.environ["ARGUMENT_LOG"]).write_text('
                "json.dumps(sys.argv[1:]))\n"
            )
            receiver.chmod(0o700)
            shell = (
                original_shell.replace(
                    "/usr/bin/python3.13", shlex.quote(str(receiver))
                )
                .replace(
                    "/opt/sku-dreamon/current/deploy/cd_release.py",
                    shlex.quote(str(current)),
                )
                .replace(
                    "/opt/sku-dreamon/operations/cd_release.py",
                    shlex.quote(str(fallback)),
                )
            )
            self.assertNotIn("/usr/bin/python3.13", shell)
            self.assertNotIn("/opt/sku-dreamon/", shell)
            log = root / "args.json"
            for use_current in (False, True):
                if use_current:
                    current.write_text(
                        'raise AssertionError("must never execute production runner")\n'
                    )
                runner = str(current if use_current else fallback)
                for action in ("status", "rollback", "deploy"):
                    with self.subTest(action=action, current=use_current):
                        source = SOURCE if action == "deploy" else "0" * 64
                        digest = DIGEST if action == "deploy" else "0" * 64
                        environment = {
                            "PATH": os.environ.get("PATH", ""),
                            "ARGUMENT_LOG": str(log),
                            "SSM_Action": action,
                            "SSM_ReleaseSha": SHA,
                            "SSM_ExpectedCurrentSha": OLD_SHA,
                            "SSM_SourceSha256": source,
                            "SSM_ImageDigest": digest,
                        }
                        result = subprocess.run(
                            ["/bin/sh", "-c", shell],
                            env=environment,
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        arguments = json.loads(log.read_text())
                        expected = [
                            runner,
                            "--config",
                            "/etc/sku-dreamon/cd.json",
                            "--action",
                            action,
                        ]
                        if action != "status":
                            expected += ["--sha", SHA]
                        if action == "deploy":
                            expected += [
                                "--source-sha256",
                                SOURCE,
                                "--image-digest",
                                DIGEST,
                            ]
                        if action != "status":
                            expected += ["--expected-current", OLD_SHA]
                        self.assertEqual(arguments, expected)
                        self.assertNotIn("0" * 64, arguments)
                        if action != "deploy":
                            self.assertNotIn("--source-sha256", arguments)
                            self.assertNotIn("--image-digest", arguments)


if __name__ == "__main__":
    unittest.main()
