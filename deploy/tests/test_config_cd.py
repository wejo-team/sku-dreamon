"""설정 배포의 권한 경계·낙관적 잠금·SSM 결과 검증을 검사한다."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import cd  # noqa: E402
import config_cd as config  # noqa: E402

SHA = "b" * 40
ACTIVE_SHA = "a" * 40
HASH = "c" * 64
PREVIOUS_HASH = "d" * 64
NEW_HASH = "e" * 64
NEW_REVISION = "ssm-7-" + "f" * 40
COMMAND = "12345678-1234-1234-1234-123456789012"
ENVIRONMENT = {
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_SHA": SHA,
    "GITHUB_REPOSITORY": config.REPOSITORY,
    "AWS_REGION": "ap-northeast-2",
    "DEPLOY_INSTANCE_ID": "i-synthetic",
    "DEPLOY_CONFIG_SSM_DOCUMENT": "synthetic-config",
}


def status(**changes):
    return {
        "phase": "stable",
        "config_phase": "idle",
        "active_sha": ACTIVE_SHA,
        "active_env_hash": HASH,
        "active_config_revision": "ssm-v2-synthetic",
        "previous_sha": ACTIVE_SHA,
        "previous_env_hash": PREVIOUS_HASH,
        "previous_config_revision": "ssm-v1-synthetic",
        **changes,
    }


def checks():
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
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, ENVIRONMENT, clear=True).start()
        self.command = patch.object(cd, "run", return_value=SHA.encode()).start()
        self.latest = patch.object(cd, "latest_main", return_value=True).start()
        self.github = patch.object(
            cd, "gh", return_value={"check_runs": checks()}
        ).start()

    def test_main_dispatch_exact_checkout_and_repository_are_required(self):
        config.gate(SHA, "apply", "7")
        for change in (
            {"GITHUB_EVENT_NAME": "push"},
            {"GITHUB_EVENT_NAME": "pull_request"},
            {"GITHUB_REF": "refs/heads/develop"},
            {"GITHUB_REF": "refs/tags/main"},
            {"GITHUB_REPOSITORY": "synthetic/fork"},
            {"GITHUB_SHA": ACTIVE_SHA},
        ):
            with self.subTest(change=change), patch.dict(os.environ, change):
                with self.assertRaises(cd.DeploymentError):
                    config.gate(SHA, "apply", "7")
        self.command.return_value = ACTIVE_SHA.encode()
        with self.assertRaises(cd.DeploymentError):
            config.gate(SHA, "apply", "7")

    def test_stale_main_or_failed_checks_prevent_mutation(self):
        self.latest.return_value = False
        with self.assertRaisesRegex(cd.DeploymentError, "superseded"):
            config.gate(SHA, "apply", "7")
        self.github.assert_not_called()
        self.latest.return_value = True
        self.github.return_value = {"check_runs": []}
        with self.assertRaisesRegex(cd.DeploymentError, "checks"):
            config.gate(SHA, "apply", "7")
        failed = checks()
        failed[0]["conclusion"] = "failure"
        self.github.return_value = {"check_runs": failed}
        with self.assertRaises(cd.DeploymentError):
            config.gate(SHA, "apply", "7")

    def test_status_and_recovery_are_independent_of_new_code_checks(self):
        self.github.return_value = {"check_runs": []}
        for action in ("status", "rollback", "recover"):
            with self.subTest(action=action):
                config.gate(SHA, action, "0")
                self.latest.return_value = False
                with self.assertRaisesRegex(cd.DeploymentError, "superseded"):
                    config.gate(SHA, action, "0")
                self.latest.return_value = True
        self.github.assert_not_called()

    def test_version_and_action_are_checked_before_external_calls(self):
        for action, version in (
            ("apply", "0"),
            ("apply", ""),
            ("apply", "01"),
            ("apply", "-1"),
            ("apply", "9223372036854775808"),
            ("apply", "7; touch injected"),
            ("rollback", "7"),
            ("recover", "7"),
            ("status", "7"),
            ("shell", "0"),
        ):
            with self.subTest(action=action, version=version):
                with self.assertRaises(cd.DeploymentError):
                    config.gate(SHA, action, version)
        self.command.assert_not_called()


class ExecuteTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        self.gate = patch.object(config, "gate").start()
        self.host = patch.object(config, "host").start()

    def test_apply_preserves_running_code_and_uses_observed_config_identity(self):
        result = status(
            active_env_hash=NEW_HASH,
            active_config_revision=NEW_REVISION,
            operation_status="applied",
        )
        self.host.side_effect = [status(), result]
        self.assertEqual(config.execute(SHA, "apply", "7"), result)
        self.assertEqual(
            self.host.call_args_list,
            [
                call("status"),
                call(
                    "apply",
                    version=7,
                    expected_sha=ACTIVE_SHA,
                    expected_env_hash=HASH,
                    expected_revision="ssm-v2-synthetic",
                ),
            ],
        )
        self.assertEqual(self.gate.call_args_list, [call(SHA, "apply", "7")] * 2)

    def test_pending_configuration_blocks_apply_and_rollback_but_allows_recover(self):
        before = status(config_phase="pending", phase="failed")
        for action in ("apply", "rollback"):
            self.host.reset_mock()
            self.host.side_effect = [before]
            with self.subTest(action=action), self.assertRaises(cd.DeploymentError):
                config.execute(SHA, action, "7" if action == "apply" else "0")
            self.assertEqual(self.host.call_count, 1)
        self.host.side_effect = [before, status(operation_status="recovered")]
        self.assertEqual(config.execute(SHA, "recover", "0")["config_phase"], "idle")

    def test_rollback_requires_same_code_and_expected_previous_environment(self):
        self.host.side_effect = [status(previous_sha=SHA)]
        with self.assertRaises(cd.DeploymentError):
            config.execute(SHA, "rollback", "0")
        self.host.side_effect = [
            status(),
            status(
                active_env_hash=PREVIOUS_HASH,
                active_config_revision="ssm-v1-synthetic",
                operation_status="rolled_back",
            ),
        ]
        self.assertEqual(
            config.execute(SHA, "rollback", "0")["active_env_hash"], PREVIOUS_HASH
        )
        self.host.side_effect = [status(), status(operation_status="rolled_back")]
        with self.assertRaisesRegex(cd.DeploymentError, "result_mismatch"):
            config.execute(SHA, "rollback", "0")
        self.host.side_effect = [
            status(),
            status(active_env_hash=PREVIOUS_HASH, operation_status="rolled_back"),
        ]
        with self.assertRaisesRegex(cd.DeploymentError, "result_mismatch"):
            config.execute(SHA, "rollback", "0")

    def test_new_main_between_status_and_apply_prevents_send(self):
        self.gate.side_effect = [None, cd.DeploymentError("config_workflow_superseded")]
        self.host.return_value = status()
        with self.assertRaises(cd.DeploymentError):
            config.execute(SHA, "apply", "7")
        self.host.assert_called_once_with("status")

    def test_wrong_code_pending_or_missing_success_result_cannot_pass(self):
        for change in (
            {"active_sha": SHA},
            {"config_phase": "pending"},
            {"phase": "failed"},
            {"operation_status": None},
            {"operation_status": "recovered"},
            {"active_config_revision": "ssm-8-" + "f" * 40},
        ):
            self.host.side_effect = [
                status(),
                status(operation_status="applied", active_config_revision=NEW_REVISION)
                | change,
            ]
            with self.subTest(change=change), self.assertRaises(cd.DeploymentError):
                config.execute(SHA, "apply", "7")


class HostTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, ENVIRONMENT, clear=True).start()
        self.aws = patch.object(
            cd, "aws", return_value={"Command": {"CommandId": COMMAND}}
        ).start()
        self.command = patch.object(config.subprocess, "run").start()
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))

    def response(self, state="Success", payload=None):
        return subprocess.CompletedProcess(
            ["aws"],
            0,
            stdout=json.dumps(
                {
                    "Status": state,
                    "StandardOutputContent": json.dumps(payload or status()),
                }
            ).encode(),
            stderr=b"",
        )

    def test_only_exact_version_and_expected_identifiers_enter_ssm_arguments(self):
        self.command.return_value = self.response(payload=status(secret="never-log"))
        result = config.host(
            "apply",
            version=7,
            expected_sha=ACTIVE_SHA,
            expected_env_hash=HASH,
            expected_revision="ssm-v2-synthetic",
        )
        args = self.aws.call_args.args
        self.assertEqual(args[:2], ("ssm", "send-command"))
        self.assertEqual(args[args.index("--document-version") + 1], "1")
        self.assertEqual(
            json.loads(args[args.index("--parameters") + 1]),
            {
                "Action": ["apply"],
                "ParameterVersion": ["7"],
                "ExpectedCurrentSha": [ACTIVE_SHA],
                "ExpectedEnvHash": [HASH],
                "ExpectedConfigRevision": ["ssm-v2-synthetic"],
            },
        )
        self.assertNotIn("secret", result)
        self.assertNotIn("never-log", self.output.getvalue())

    def test_failed_command_does_not_accept_success_payload_or_echo_remote_logs(self):
        self.command.return_value = self.response("Failed", {"secret": "never-log"})
        with self.assertRaisesRegex(cd.DeploymentError, "command_failed") as error:
            config.host("status")
        self.assertNotIn("never-log", str(error.exception) + self.output.getvalue())

    def test_only_fixed_host_recovery_outcomes_are_propagated(self):
        for code in (*config.HOST_ERRORS, "private-credential-never-log"):
            response = self.response("Failed")
            invocation = json.loads(response.stdout)
            invocation["StandardErrorContent"] = (
                "private diagnostic never-log\n" + json.dumps({"error": code})
            )
            response.stdout = json.dumps(invocation).encode()
            self.command.return_value = response
            with (
                self.subTest(code=code),
                self.assertRaises(cd.DeploymentError) as error,
            ):
                config.host("status")
            self.assertEqual(
                str(error.exception),
                code if code in config.HOST_ERRORS else "config_host_command_failed",
            )
            self.assertNotIn("never-log", str(error.exception) + self.output.getvalue())

    def test_unknown_outcome_is_bounded_and_does_not_resubmit(self):
        self.command.side_effect = subprocess.TimeoutExpired("private-data", 5)
        with patch.object(config.time, "monotonic", side_effect=[0, 1845, 1845]):
            with self.assertRaisesRegex(cd.DeploymentError, "outcome_unknown") as error:
                config.host("status")
        self.assertLessEqual(self.command.call_args.kwargs["timeout"], 5)
        self.aws.assert_called_once()
        self.assertNotIn("private-data", str(error.exception))

    def test_eventual_visibility_and_pending_poll_until_success(self):
        self.command.side_effect = [
            subprocess.CompletedProcess(
                ["aws"], 1, stdout=b"", stderr=b"InvocationDoesNotExist"
            ),
            self.response("InProgress"),
            self.response(),
        ]
        with patch.object(config.time, "sleep"):
            self.assertEqual(config.host("status"), status())
        self.aws.assert_called_once()

    def test_malformed_or_unsafe_status_is_rejected_without_disclosure(self):
        for payload in (
            {"secret": "never-log"},
            status(active_sha="never-log"),
            status(active_env_hash="never-log"),
            status(active_config_revision="unsafe\nrevision"),
            status(previous_env_hash=None),
            status(operation_status="never-log"),
        ):
            self.command.return_value = self.response(payload=payload)
            with (
                self.subTest(payload=payload),
                self.assertRaises(cd.DeploymentError) as error,
            ):
                config.host("status")
            self.assertNotIn("never-log", str(error.exception) + self.output.getvalue())


class SSMDocumentTests(unittest.TestCase):
    def test_shell_passes_unexpanded_arguments_only_to_the_fixed_runner(self):
        document = json.loads((DEPLOY / "ssm-production-config.json").read_text())
        parameters = document["parameters"]
        self.assertTrue(
            all(p["interpolationType"] == "ENV_VAR" for p in parameters.values())
        )
        shell = "\n".join(document["mainSteps"][0]["inputs"]["runCommand"])
        self.assertNotIn("{{", shell)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "config_release.py"
            runner.write_text("unused\n")
            receiver = root / "fake-python"
            receiver.write_text(
                f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
                'Path(os.environ["ARGUMENT_LOG"]).write_text(json.dumps(sys.argv[1:]))\n'
            )
            receiver.chmod(0o700)
            shell = shell.replace(
                "/usr/bin/python3.13", shlex.quote(str(receiver))
            ).replace(
                "/opt/sku-dreamon/current/deploy/config_release.py",
                shlex.quote(str(runner)),
            )
            log = root / "args.json"
            for action in config.ACTIONS:
                env = {
                    **os.environ,
                    "ARGUMENT_LOG": str(log),
                    "SSM_Action": action,
                    "SSM_ParameterVersion": "7" if action == "apply" else "0",
                    "SSM_ExpectedCurrentSha": ACTIVE_SHA,
                    "SSM_ExpectedEnvHash": HASH,
                    "SSM_ExpectedConfigRevision": "ssm-v2-synthetic",
                }
                subprocess.run(
                    ["sh", "-c", shell], check=True, env=env, capture_output=True
                )
                args = json.loads(log.read_text())
                self.assertEqual(args[0], str(runner))
                self.assertEqual(args[args.index("--action") + 1], action)
                self.assertEqual(
                    args[args.index("--version") + 1], env["SSM_ParameterVersion"]
                )
            injected = "$(touch " + str(root / "injected") + ")"
            self.assertIsNone(
                re.fullmatch(parameters["ParameterVersion"]["allowedPattern"], injected)
            )
            # Agent의 pattern 검사와 별개로 shell은 값 안의 치환도 실행하지 않는다.
            env["SSM_ParameterVersion"] = injected
            subprocess.run(
                ["sh", "-c", shell], check=True, env=env, capture_output=True
            )
            self.assertFalse((root / "injected").exists())
            self.assertIn(injected, json.loads(log.read_text()))
            env["SSM_Action"] = "shell"
            self.assertEqual(
                subprocess.run(
                    ["sh", "-c", shell], env=env, capture_output=True
                ).returncode,
                2,
            )
            runner.unlink()
            env["SSM_Action"] = "status"
            self.assertNotEqual(
                subprocess.run(
                    ["sh", "-c", shell], env=env, capture_output=True
                ).returncode,
                0,
            )


if __name__ == "__main__":
    unittest.main()
