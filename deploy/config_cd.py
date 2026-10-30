"""검증된 main에서 값 노출 없이 현재 앱의 설정 교체·복구를 요청한다."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cd

REPOSITORY = "wejo-team/sku-dreamon"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}\Z")
ACTIONS = ("apply", "rollback", "recover", "status")
ZERO_SHA = "0" * 40
ZERO_DIGEST = "0" * 64
HOST_ERRORS = frozenset(
    {"configuration_failed_restored", "configuration_recovery_required"}
)


def request(action: str, version: str) -> int:
    """SSM에 보내기 전에 동작별 입력을 제한한다."""
    if action not in ACTIONS:
        raise cd.DeploymentError("invalid_config_action")
    if not re.fullmatch(r"0|[1-9][0-9]{0,18}", version):
        raise cd.DeploymentError("invalid_parameter_version")
    number = int(version)
    if number > 9_223_372_036_854_775_807 or (action == "apply") != (number > 0):
        raise cd.DeploymentError("invalid_parameter_version")
    return number


def gate(sha: str, action: str, version: str) -> None:
    request(action, version)
    if (
        not SHA.fullmatch(sha)
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or os.environ.get("GITHUB_SHA") != sha
        or cd.run("git", "rev-parse", "HEAD").decode().strip() != sha
    ):
        raise cd.DeploymentError("config_requires_main_dispatch_checkout")
    if not cd.latest_main(sha):
        raise cd.DeploymentError("config_workflow_superseded")
    # 이미 적용된 설정의 복구는 새 main의 업무 코드 검사 실패와 독립적이다.
    if action == "apply":
        checks = cd.gh(f"repos/{REPOSITORY}/commits/{sha}/check-runs?per_page=100")
        if not cd.successful_checks(checks["check_runs"]):
            raise cd.DeploymentError("config_requires_successful_checks")


def safe_status(value: Any) -> dict[str, Any]:
    """원격 출력은 알려진 상태·식별자만 받아 로그에 남긴다."""
    if not isinstance(value, dict):
        raise cd.DeploymentError("invalid_config_status")
    result = {
        key: value.get(key)
        for key in (
            "phase",
            "config_phase",
            "active_sha",
            "active_env_hash",
            "active_config_revision",
            "previous_sha",
            "previous_env_hash",
            "previous_config_revision",
        )
    }
    if result["phase"] not in {"stable", "pending", "failed"} or result[
        "config_phase"
    ] not in {"idle", "pending"}:
        raise cd.DeploymentError("invalid_config_status")
    for prefix in ("active", "previous"):
        items = [
            result[f"{prefix}_{key}"] for key in ("sha", "env_hash", "config_revision")
        ]
        if prefix == "previous" and all(item is None for item in items):
            continue
        if any(
            not isinstance(item, str) or not pattern.fullmatch(item)
            for item, pattern in zip(items, (SHA, DIGEST, REVISION), strict=True)
        ):
            raise cd.DeploymentError("invalid_config_status")
    operation = value.get("operation_status")
    if operation is not None:
        if operation not in {"applied", "rolled_back", "recovered", "unchanged"}:
            raise cd.DeploymentError("invalid_config_status")
        result["operation_status"] = operation
    return result


def host(
    action: str,
    *,
    version: int = 0,
    expected_sha: str = ZERO_SHA,
    expected_env_hash: str = ZERO_DIGEST,
    expected_revision: str = "unknown",
) -> dict[str, Any]:
    request(action, str(version))
    if (
        not SHA.fullmatch(expected_sha)
        or not DIGEST.fullmatch(expected_env_hash)
        or not REVISION.fullmatch(expected_revision)
    ):
        raise cd.DeploymentError("invalid_expected_configuration")
    parameters = {
        "Action": [action],
        "ParameterVersion": [str(version)],
        "ExpectedCurrentSha": [expected_sha],
        "ExpectedEnvHash": [expected_env_hash],
        "ExpectedConfigRevision": [expected_revision],
    }
    command = cd.aws(
        "ssm",
        "send-command",
        "--instance-ids",
        os.environ["DEPLOY_INSTANCE_ID"],
        "--document-name",
        os.environ["DEPLOY_CONFIG_SSM_DOCUMENT"],
        "--document-version",
        "1",
        "--parameters",
        json.dumps(parameters),
        "--timeout-seconds",
        "120",
        "--comment",
        f"GitHub production configuration: {action}",
        timeout=60,
    )["Command"]["CommandId"]
    if not isinstance(command, str) or not re.fullmatch(
        r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", command
    ):
        raise cd.DeploymentError("invalid_ssm_command_identity")
    print(json.dumps({"action": action, "command_id": command}), flush=True)
    deadline = time.monotonic() + 1850
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                [
                    "aws",
                    "ssm",
                    "get-command-invocation",
                    "--command-id",
                    command,
                    "--instance-id",
                    os.environ["DEPLOY_INSTANCE_ID"],
                    "--region",
                    os.environ["AWS_REGION"],
                    "--output",
                    "json",
                ],
                capture_output=True,
                check=False,
                timeout=max(1, min(60, deadline - time.monotonic())),
            )
        except (OSError, subprocess.TimeoutExpired):
            raise cd.DeploymentError("config_ssm_outcome_unknown") from None
        if result.returncode:
            if b"InvocationDoesNotExist" in result.stderr:
                time.sleep(3)
                continue
            raise cd.DeploymentError("config_ssm_outcome_unknown")
        try:
            invocation = json.loads(result.stdout)
            state = invocation["Status"]
            if state in {"Pending", "InProgress", "Delayed", "Cancelling"}:
                time.sleep(5)
                continue
            if state != "Success":
                error_output = invocation.get("StandardErrorContent", "")
                if isinstance(error_output, str) and len(error_output) <= 65536:
                    try:
                        error = json.loads(error_output.strip().splitlines()[-1])
                        code = error.get("error") if isinstance(error, dict) else None
                        if isinstance(code, str) and code in HOST_ERRORS:
                            raise cd.DeploymentError(code)
                    except (ValueError, IndexError):
                        pass
                raise cd.DeploymentError("config_host_command_failed")
            output = invocation["StandardOutputContent"]
            if not isinstance(output, str) or len(output) > 65536:
                raise cd.DeploymentError("invalid_config_status")
            return safe_status(json.loads(output.strip().splitlines()[-1]))
        except (ValueError, KeyError, TypeError, IndexError):
            raise cd.DeploymentError("invalid_config_status") from None
    raise cd.DeploymentError("config_ssm_outcome_unknown")


def execute(sha: str, action: str, version: str) -> dict[str, Any]:
    gate(sha, action, version)
    before = host("status")
    if action == "status":
        return before
    if action != "recover" and (
        before["phase"] != "stable" or before["config_phase"] != "idle"
    ):
        raise cd.DeploymentError("configuration_requires_recovery")
    if action == "rollback" and (
        before["previous_sha"] != before["active_sha"]
        or before["previous_env_hash"] is None
    ):
        raise cd.DeploymentError("no_previous_configuration_for_current_code")
    # 상태 조회 뒤 새 main이 들어와도 과거 workflow가 운영 설정을 바꾸지 않는다.
    gate(sha, action, version)
    result = host(
        action,
        version=int(version),
        expected_sha=before["active_sha"],
        expected_env_hash=before["active_env_hash"],
        expected_revision=before["active_config_revision"],
    )
    if (
        result["active_sha"] != before["active_sha"]
        or result["phase"] != "stable"
        or result["config_phase"] != "idle"
        or result.get("operation_status")
        not in {
            "unchanged",
            {"apply": "applied", "rollback": "rolled_back", "recover": "recovered"}[
                action
            ],
        }
        or (
            action == "rollback"
            and (
                result["active_env_hash"] != before["previous_env_hash"]
                or result["active_config_revision"]
                != before["previous_config_revision"]
            )
        )
        or (
            action == "apply"
            and not re.fullmatch(
                rf"ssm-{int(version)}-[0-9a-f]{{40}}", result["active_config_revision"]
            )
        )
    ):
        raise cd.DeploymentError("configuration_result_mismatch")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Production configuration deployment")
    parser.add_argument("command", choices=("gate", "run"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--action", required=True, choices=ACTIONS)
    parser.add_argument("--version", default="0")
    args = parser.parse_args()
    try:
        if args.command == "gate":
            gate(args.sha, args.action, args.version)
            return 0
        result = execute(args.sha, args.action, args.version)
        print(json.dumps(result))
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
                summary.write(
                    f"Configuration action: `{args.action}`; "
                    f"code: `{result['active_sha']}`; "
                    f"configuration: `{result['active_config_revision']}`; "
                    f"state: `{result['config_phase']}`.\n"
                )
        return 0
    except Exception as error:  # noqa: BLE001 -- 외부 실패 원문과 원격 출력은 공개하지 않는다.
        code = (
            str(error)
            if isinstance(error, cd.DeploymentError) and str(error) in HOST_ERRORS
            else "configuration_workflow_failed"
        )
        print(
            json.dumps({"error": code, "next_action": "inspect_host_status"}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
