"""PR 전체 diff의 검사 영역과 릴리스 PR의 E2E 실행 여부를 판별한다."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

AREAS = ("frontend", "backend", "docs", "deployment")
CHECKS = (*AREAS, "integration")
DOC_FILES = {
    "README.md",
    "AGENTS.md",
    "package.json",
    "package-lock.json",
    ".nvmrc",
    "scripts/check_docs.py",
    "scripts/check_docs_site.py",
    "scripts/tests/test_check_docs.py",
    "scripts/tests/test_check_docs_site.py",
}


class ScopeError(ValueError):
    """Scope cannot be established safely."""


def classify_paths(paths: Iterable[str]) -> set[str]:
    selected: set[str] = set()
    for path in paths:
        if path.startswith(("docs/", "design-reference/")) or path in DOC_FILES:
            selected.add("docs")
        elif path.startswith("frontend/"):
            selected.add("frontend")
        elif path.startswith("backend/"):
            selected.add("backend")
            if path == "backend/Dockerfile":
                selected.add("deployment")
        else:
            # New/shared tooling has no established isolation guarantee.
            return set(AREAS)
    return selected or set(AREAS)


def git(*arguments: str) -> bytes:
    result = subprocess.run(["git", *arguments], capture_output=True, check=False)
    if result.returncode:
        raise ScopeError(
            f"git {arguments[0]} failed; both PR commits and their history are required"
        )
    return result.stdout


def pr_changed_paths(event: dict) -> list[str]:
    try:
        base = event["pull_request"]["base"]["sha"]
        head = event["pull_request"]["head"]["sha"]
    except (KeyError, TypeError):
        raise ScopeError("pull_request base/head SHAs are required") from None
    if any(
        not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha)
        for sha in (base, head)
    ):
        raise ScopeError("pull_request base/head SHAs must be 40 hex characters")
    git("merge-base", base, head)
    changed = git(
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--name-only",
        "-z",
        "--no-renames",
        f"{base}...{head}",
        "--",
    )
    if changed and not changed.endswith(b"\0"):
        raise ScopeError("git diff did not return NUL-delimited paths")
    # No rename detection: a move contributes both its deleted and added paths.
    return [os.fsdecode(path) for path in changed.split(b"\0") if path]


def is_release_pr(event: dict) -> bool:
    branches = []
    for side in ("base", "head"):
        try:
            branch = event["pull_request"][side]
            ref = branch["ref"]
            repository_id = branch["repo"]["id"]
        except (KeyError, TypeError):
            raise ScopeError("PR branch refs and repository IDs are required") from None
        if not isinstance(ref, str) or not ref:
            raise ScopeError("PR branch refs must be nonempty strings")
        if type(repository_id) is not int or repository_id <= 0:
            raise ScopeError("PR repository IDs must be positive integers")
        branches.append((ref, repository_id))
    (base, base_repository), (head, head_repository) = branches
    return base == "main" and head == "develop" and base_repository == head_repository


def detect_scope(environment: Mapping[str, str]) -> tuple[set[str], str]:
    event = environment.get("GITHUB_EVENT_NAME", "")
    if event == "workflow_dispatch":
        return set(AREAS), "Manual run: all areas; E2E only runs for release PRs."
    if event == "push" and environment.get("GITHUB_REF") in {
        "refs/heads/develop",
        "refs/heads/main",
    }:
        branch = environment["GITHUB_REF"].removeprefix("refs/heads/")
        return (
            set(AREAS),
            f"Push to {branch}: all areas; E2E only runs for release PRs.",
        )
    if event == "pull_request":
        event_path = environment.get("GITHUB_EVENT_PATH", "")
        if not event_path:
            raise ScopeError("GITHUB_EVENT_PATH is required for pull_request")
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        paths = pr_changed_paths(payload)
        selected = classify_paths(paths)
        reason = (
            "Entire PR diff since the merge base; shared or unknown paths select all areas."
            if paths
            else "Empty PR diff: all areas as a precaution."
        )
        if is_release_pr(payload):
            selected.add("integration")
            reason += " Same-repository develop -> main release PR: E2E required."
        else:
            reason += " Not a release PR: E2E not required."
        return selected, reason
    raise ScopeError("unsupported event or push ref")


def main() -> int:
    try:
        selected, reason = detect_scope(os.environ)
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            raise ScopeError("GITHUB_OUTPUT is required")
        output = "".join(f"{area}={str(area in selected).lower()}\n" for area in CHECKS)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            summary = "## CI scope\n\n" + reason + "\n\n| Area | Run |\n| --- | --- |\n"
            summary += "".join(
                f"| {area} | {'yes' if area in selected else 'no'} |\n"
                for area in CHECKS
            )
            with Path(summary_path).open("a", encoding="utf-8") as stream:
                stream.write(summary)
        # Publish no successful area outputs until classification has completed.
        with Path(output_path).open("a", encoding="utf-8") as stream:
            stream.write(output)
        print(output, end="")
    except (ScopeError, OSError, json.JSONDecodeError) as error:
        message = str(error) if isinstance(error, ScopeError) else type(error).__name__
        print(f"CI scope detection failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
