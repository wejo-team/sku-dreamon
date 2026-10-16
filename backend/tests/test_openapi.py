import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.export_openapi import render_openapi

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_export_uses_routes_without_starting_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_database_start(url: str) -> None:
        pytest.fail("Exporting OpenAPI must not start the database")

    monkeypatch.setattr("app.factory.create_database", unexpected_database_start)
    monkeypatch.setenv("DATABASE_URL", "invalid-runtime-setting")

    content = render_openapi()
    schema = json.loads(content)
    response = schema["paths"]["/api/v1/health"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
    assert schema["components"]["schemas"]["HealthResponse"]["required"] == ["status"]
    assert render_openapi() == content


def test_export_cli_is_independent_of_env_and_detects_drift(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DATABASE_URL=invalid-dotenv-setting\n")
    output = tmp_path / "contract.json"
    env = {
        **os.environ,
        "DATABASE_URL": "invalid-environment-setting",
        "PYTHONPATH": str(BACKEND_ROOT),
    }

    def run_export(*options: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.export_openapi",
                "--output",
                str(output),
                *options,
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    assert run_export("--check").returncode == 1
    assert not output.exists()
    generated = run_export()
    assert generated.returncode == 0, generated.stderr
    first = output.read_bytes()
    assert b"\r" not in first
    assert first.endswith(b"\n")
    assert run_export().returncode == 0
    assert output.read_bytes() == first
    assert run_export("--check").returncode == 0

    changed = json.loads(first)
    changed["paths"].pop("/api/v1/health")
    stale = json.dumps(changed).encode()
    output.write_bytes(stale)
    result = run_export("--check")
    assert result.returncode == 1
    assert "missing or stale" in result.stderr
    assert output.read_bytes() == stale
