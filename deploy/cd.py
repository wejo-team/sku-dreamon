"""검증된 main 커밋의 API·프런트 배포와 실패 복구를 조합한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class DeploymentError(RuntimeError):
    """비밀값이나 하위 명령의 원문을 포함하지 않는 배포 실패."""


def run(*args: str, data: bytes | None = None, timeout: int = 900) -> bytes:
    result = subprocess.run(
        args, input=data, capture_output=True, timeout=timeout, check=False
    )
    if result.returncode:
        raise DeploymentError(f"{args[0]} {args[1]} failed ({result.returncode})")
    return result.stdout


def gh(path: str) -> Any:
    return json.loads(run("gh", "api", path, timeout=30))


def latest_main(sha: str) -> bool:
    repository = os.environ["GITHUB_REPOSITORY"]
    return gh(f"repos/{repository}/commits/main")["sha"] == sha


def validate_context(sha: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise DeploymentError("invalid release SHA")
    if (
        os.environ.get("GITHUB_EVENT_NAME") != "push"
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_SHA") != sha
        or run("git", "rev-parse", "HEAD").decode().strip() != sha
    ):
        raise DeploymentError("production requires the exact main push checkout")


def successful_checks(checks: list[dict[str, Any]]) -> bool:
    for name in ("Frontend", "Backend", "Validate docs"):
        matching = [
            check
            for check in checks
            if check["name"] == name
            and check.get("app", {}).get("slug") == "github-actions"
        ]
        if not matching:
            return False
        newest = max(matching, key=lambda check: check["id"])
        if newest["status"] != "completed":
            return False
        if newest["conclusion"] != "success":
            raise DeploymentError(f"required check failed: {name}")
    return True


def gate(sha: str, timeout: int = 900) -> bool:
    validate_context(sha)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not latest_main(sha):
            return False
        repository = os.environ["GITHUB_REPOSITORY"]
        checks = gh(f"repos/{repository}/commits/{sha}/check-runs?per_page=100")
        if successful_checks(checks["check_runs"]):
            return True
        time.sleep(10)
    raise DeploymentError("required checks did not complete within the gate deadline")


def aws(*args: str, timeout: int = 900) -> Any:
    output = run(
        "aws",
        *args,
        "--region",
        os.environ["AWS_REGION"],
        "--output",
        "json",
        timeout=timeout,
    )
    return json.loads(output) if output.strip() else {}


def host(
    action: str,
    *,
    sha: str = "0" * 40,
    source: str = "0" * 64,
    digest: str = "0" * 64,
    expected: str = "0" * 40,
) -> dict[str, Any]:
    parameters = {
        "Action": [action],
        "ReleaseSha": [sha],
        "SourceSha256": [source],
        "ImageDigest": [digest],
        "ExpectedCurrentSha": [expected],
    }
    command = aws(
        "ssm",
        "send-command",
        "--instance-ids",
        os.environ["DEPLOY_INSTANCE_ID"],
        "--document-name",
        os.environ["DEPLOY_SSM_DOCUMENT"],
        "--document-version",
        "1",
        "--parameters",
        json.dumps(parameters),
        "--timeout-seconds",
        "120",
        "--comment",
        f"GitHub production {action}: {sha[:12]}",
    )["Command"]["CommandId"]
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
        except subprocess.TimeoutExpired:
            raise DeploymentError(
                f"SSM command {command} outcome unknown; inspect before retry"
            ) from None
        if result.returncode:
            if b"InvocationDoesNotExist" in result.stderr:
                time.sleep(3)
                continue
            raise DeploymentError(f"cannot inspect SSM command {command}")
        invocation = json.loads(result.stdout)
        status = invocation["Status"]
        if status in {"Pending", "InProgress", "Delayed", "Cancelling"}:
            time.sleep(5)
            continue
        if status != "Success":
            raise DeploymentError(f"SSM command {command} ended with {status}")
        lines = invocation["StandardOutputContent"].strip().split("\n")
        try:
            return json.loads(lines[-1])
        except (ValueError, IndexError):
            raise DeploymentError("host returned no valid deployment result") from None
    raise DeploymentError(
        f"SSM command {command} outcome unknown; inspect before retry"
    )


def image(sha: str, state_dir: Path) -> str:
    repository = os.environ["ECR_REPOSITORY_URL"]
    registry, name = repository.split("/", 1)
    if not re.fullmatch(r"[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com", registry):
        raise DeploymentError("invalid ECR registry")
    existing = aws(
        "ecr", "list-images", "--repository-name", name, "--filter", "tagStatus=TAGGED"
    )
    found = next(
        (
            item["imageDigest"]
            for item in existing["imageIds"]
            if item.get("imageTag") == sha
        ),
        None,
    )
    if found is None:
        tag = f"{repository}:{sha}"
        run(
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--file",
            "backend/Dockerfile",
            "--build-arg",
            f"RELEASE_SHA={sha}",
            "--tag",
            tag,
            ".",
            timeout=1200,
        )
        with tempfile.TemporaryDirectory(dir=state_dir, prefix="ecr-") as temporary:
            token = run(
                "aws", "ecr", "get-login-password", "--region", os.environ["AWS_REGION"]
            )
            run(
                "docker",
                "--config",
                temporary,
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                registry,
                data=token,
            )
            run("docker", "--config", temporary, "push", tag, timeout=1200)
    found = aws(
        "ecr",
        "describe-images",
        "--repository-name",
        name,
        "--image-ids",
        f"imageTag={sha}",
    )["imageDetails"][0]["imageDigest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", found):
        raise DeploymentError("registry returned an invalid digest")
    return found.removeprefix("sha256:")


def verify_api(sha: str) -> None:
    base = os.environ["API_BASE_URL"].rstrip("/")
    origin = os.environ["SITE_URL"].rstrip("/")
    if any(urlsplit(value).scheme != "https" for value in (base, origin)):
        raise DeploymentError("public verification requires HTTPS")
    request = Request(base + "/health", headers={"Origin": origin})
    with urlopen(request, timeout=20) as response:
        if (
            response.status != 200
            or response.url != base + "/health"
            or response.headers.get("X-Release-ID") != sha
            or response.headers.get("Access-Control-Allow-Origin") != origin
            or response.headers.get("Access-Control-Allow-Credentials") != "true"
            or json.load(response) != {"status": "ok"}
        ):
            raise DeploymentError("public API release or CORS verification failed")


def preserve_recovery(state_dir: Path, sha: str) -> None:
    """실패한 웹 복구 자료만 비공개 배포 저장소에 보존한다."""
    frontend = state_dir / "frontend"
    try:
        if not frontend.exists():
            return
        archive = state_dir / "frontend-recovery.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            output.add(frontend, arcname="frontend")
        execution = os.environ.get("GITHUB_RUN_ID", "local")
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        if not re.fullmatch(r"[0-9]+", execution) or not re.fullmatch(
            r"[0-9]+", attempt
        ):
            execution, attempt = "local", "1"
        key = f"artifacts/cd/{sha}/recovery/{execution}-{attempt}.tar.gz"
        aws(
            "s3api",
            "put-object",
            "--bucket",
            os.environ["ARTIFACT_BUCKET"],
            "--key",
            key,
            "--body",
            str(archive),
            "--content-type",
            "application/gzip",
            timeout=30,
        )
        print(json.dumps({"private_recovery_key": key}), flush=True)
    except Exception:  # noqa: BLE001 -- 증거 보존 실패가 서비스 복구를 막으면 안 된다.
        # 증거 업로드 실패도 원래 복구 시도를 막지 않는다. 로컬 자료는 삭제하지 않는다.
        print(
            json.dumps({"recovery_upload": "failed", "local_state_preserved": True}),
            flush=True,
        )


def deploy(sha: str) -> dict[str, Any]:
    from cd_frontend import PublicationError, publish

    validate_context(sha)
    if not latest_main(sha):
        return {"status": "skipped", "reason": "superseded_main"}
    state_dir = Path(
        tempfile.mkdtemp(prefix="dreamon-cd-", dir=os.environ.get("RUNNER_TEMP"))
    )
    digest = image(sha, state_dir)
    archive = state_dir / "source.tar.gz"
    run("git", "archive", "--format=tar.gz", f"--output={archive}", sha)
    source = hashlib.sha256(archive.read_bytes()).hexdigest()
    if not latest_main(sha):
        return {"status": "skipped", "reason": "superseded_main"}
    aws(
        "s3api",
        "put-object",
        "--bucket",
        os.environ["ARTIFACT_BUCKET"],
        "--key",
        f"artifacts/cd/{sha}/source.tar.gz",
        "--body",
        str(archive),
        "--metadata",
        f"sha256={source},release-sha={sha}",
    )
    before = host("status")
    if before["phase"] != "stable":
        raise DeploymentError("host requires recovery before another deployment")
    previous = before["active_sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", previous):
        raise DeploymentError("a verified previous production release is required")
    host("deploy", sha=sha, source=source, digest=digest, expected=previous)
    try:
        verify_api(sha)
        frontend = publish(
            dist=Path("frontend/dist"),
            sha=sha,
            bucket=os.environ["FRONTEND_BUCKET"],
            distribution_id=os.environ["CLOUDFRONT_DISTRIBUTION_ID"],
            site_url=os.environ["SITE_URL"],
            api_base_url=os.environ["API_BASE_URL"],
            state_dir=state_dir / "frontend",
        )
    except Exception as error:  # noqa: BLE001 -- 게시·검증 실패 종류와 무관하게 복구한다.
        preserve_recovery(state_dir, sha)
        safe_to_rollback = (
            not isinstance(error, PublicationError) or error.rollback_succeeded
        )
        if safe_to_rollback and previous != sha:
            host("rollback", sha=previous, expected=sha)
            verify_api(previous)
            print(json.dumps({"status": "rolled_back", "sha": previous}), flush=True)
        if not safe_to_rollback:
            raise DeploymentError(
                "frontend restore incomplete; inspect production state"
            ) from None
        raise DeploymentError("publication failed; previous release restored") from None
    return {
        "status": "deployed",
        "sha": sha,
        "previous_sha": previous,
        "frontend": frontend,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("gate", "deploy"))
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        if args.action == "gate":
            current = gate(args.sha)
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
                output.write(f"current={str(current).lower()}\n")
            print(json.dumps({"current_main": current}))
        else:
            result = deploy(args.sha)
            print(json.dumps(result))
            if os.environ.get("GITHUB_STEP_SUMMARY"):
                with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
                    summary.write(
                        f"Production release: `{args.sha}` — {result['status']}\n"
                    )
        return 0
    except (
        DeploymentError,
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        message = (
            str(error) if isinstance(error, DeploymentError) else type(error).__name__
        )
        print(f"::error::{message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
