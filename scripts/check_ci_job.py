"""Keep required checks failing when scope detection or selected tests fail."""

import os
import sys


def validate_result(scope_result: str, required: str, check_result: str) -> None:
    if scope_result != "success":
        raise ValueError("CI scope detection must succeed before checks can pass.")
    if required == "true" and check_result == "success":
        return
    if required == "false" and check_result == "skipped":
        return
    raise ValueError(
        "Selected checks must succeed; only explicitly unaffected checks may be skipped."
    )


def main() -> int:
    required = os.environ.get("CHECK_REQUIRED", "")
    try:
        validate_result(
            os.environ.get("SCOPE_RESULT", ""),
            required,
            os.environ.get("CHECK_RESULT", ""),
        )
    except ValueError as error:
        print(f"Required CI check failed: {error}", file=sys.stderr)
        return 1

    print(
        "Selected checks passed."
        if required == "true"
        else "No affected files; this area's tests were not required."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
