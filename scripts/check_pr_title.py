"""Validate a pull request title from GitHub's event file without shell evaluation."""

import json
import os
import re
import sys
from pathlib import Path


ALLOWED_TYPES = ("feat", "fix", "refactor", "test", "docs", "chore", "ci")
TITLE_PATTERN = re.compile(
    rf"(?:{'|'.join(ALLOWED_TYPES)})(?:\((?P<scope>[^()]+)\))?:(?P<subject>.*)"
)


def validate_title(title: str) -> None:
    if not isinstance(title, str):
        raise ValueError("The pull request title must be a string.")
    if "\n" in title or "\r" in title:
        raise ValueError("The pull request title must fit on one line.")

    match = TITLE_PATTERN.fullmatch(title)
    if not match:
        raise ValueError(
            "Use type(scope): description, with an optional non-empty scope. "
            f"Allowed types: {', '.join(ALLOWED_TYPES)}."
        )
    if match["scope"] is not None and not match["scope"].strip():
        raise ValueError("A declared scope must not be empty.")
    if not match["subject"].strip():
        raise ValueError("Add a non-empty description after the colon.")


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("GITHUB_EVENT_PATH is required.", file=sys.stderr)
        return 1

    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        validate_title(event["pull_request"]["title"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"PR title validation failed: {error}", file=sys.stderr)
        return 1

    print("PR title follows the repository convention.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
