"""PR 이벤트 메타데이터로 브랜치 방향을 검사하고 이름을 명령으로 실행하지 않는다."""

import json
import os
import re
import sys
from pathlib import Path

WORK_BRANCH = re.compile(
    r"(?:feat|fix|refactor|test|docs|chore|ci)/[a-z0-9]+(?:-[a-z0-9]+)*"
)


class BranchPolicyError(ValueError):
    """PR 브랜치 방향을 안전하게 판별할 수 없을 때 발생한다."""


def branch_details(value: object) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise BranchPolicyError("Both PR branches must include repository metadata.")
    ref, repository = value.get("ref"), value.get("repo")
    if not isinstance(ref, str) or not ref or not isinstance(repository, dict):
        raise BranchPolicyError("Both PR branches must include a ref and repository.")
    repository_id = repository.get("id")
    if type(repository_id) is not int or repository_id <= 0:
        raise BranchPolicyError("Both PR repositories must have a valid numeric ID.")
    return ref, repository_id


def validate_branch_policy(pull_request: object) -> None:
    if not isinstance(pull_request, dict):
        raise BranchPolicyError("The event must contain a pull_request object.")
    base, base_repository = branch_details(pull_request.get("base"))
    head, head_repository = branch_details(pull_request.get("head"))
    same_repository = base_repository == head_repository
    if base == "main":
        if head != "develop" or not same_repository:
            raise BranchPolicyError("Only this repository's develop may target main.")
        return
    if base == "develop":
        if WORK_BRANCH.fullmatch(head) or (head == "main" and same_repository):
            return
        raise BranchPolicyError(
            "Target develop from a type/work-name branch or this repository's main."
        )
    raise BranchPolicyError("PRs must target develop or main.")


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("GITHUB_EVENT_PATH is required.", file=sys.stderr)
        return 1
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        validate_branch_policy(event["pull_request"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        # 브랜치 이름 등 신뢰하지 않는 이벤트 값은 로그에 남기지 않는다.
        detail = (
            str(error) if isinstance(error, BranchPolicyError) else type(error).__name__
        )
        print(f"PR branch validation failed: {detail}", file=sys.stderr)
        return 1
    print("PR branches follow the develop/main policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
