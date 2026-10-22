"""DB 기반과 예외 정의가 HTTP 계층·개별 도메인에 의존하지 않는지 검증한다."""

import subprocess
import sys
from pathlib import Path


def test_db_and_exceptions_import_without_http_or_domains() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib
import sys

for module in (
    "app.core.db.base",
    "app.core.db.check",
    "app.core.db.mixins",
    "app.core.db.session",
    "app.core.db.types",
    "app.core.exceptions",
):
    importlib.import_module(module)

unexpected = [
    name for name in sys.modules
    if name.split(".")[0] in {"fastapi", "starlette"}
    or name == "app.core.http"
    or name.startswith("app.core.http.")
    or name == "app.domains"
    or name.startswith("app.domains.")
]
assert not unexpected, f"Unexpected HTTP or domain dependencies: {unexpected}"
""",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
