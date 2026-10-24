"""DB 기반과 예외 정의가 HTTP 계층·업무 레이어에 의존하지 않는지 검증한다."""

import subprocess
import sys
from pathlib import Path


def test_db_and_exceptions_import_without_http_or_business_layers() -> None:
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
    "app.core.db.factories",
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
    or any(
        name == layer or name.startswith(layer + ".")
        for layer in (
            "app.models", "app.schemas", "app.queries", "app.services",
            "app.routers", "app.dependencies", "app.rules", "app.security",
        )
    )
]
assert not unexpected, f"Unexpected HTTP or business layer dependencies: {unexpected}"
""",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
