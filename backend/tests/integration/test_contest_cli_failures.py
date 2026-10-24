"""실제 CLI 프로세스에서 파일 오류와 DB 연결 오류의 출력 계약을 확인한다."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

from tests.unit.test_contest_import import payload

pytestmark = pytest.mark.integration


def invoke(tmp_path: Path, url: str) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "confirmed.json"
    source.write_text(json.dumps(payload()))
    return subprocess.run(
        [sys.executable, "-m", "app.cli.contests", str(source), "--apply"],
        env={**os.environ, "DATABASE_URL": url},
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def test_connection_refused_is_database_error(tmp_path: Path) -> None:
    result = invoke(
        tmp_path, "postgresql+asyncpg://nobody:private-marker@127.0.0.1:1/missing"
    )
    assert result.returncode == 1
    assert result.stderr.strip() == '{"error": "DATABASE_ERROR"}'
    assert not result.stdout


@pytest.mark.database
def test_missing_database_never_prints_driver_traceback(
    tmp_path: Path, database_url: str
) -> None:
    url = make_url(database_url).set(database=f"missing_cli_{uuid4().hex}")
    result = invoke(tmp_path, url.render_as_string(hide_password=False))
    assert result.returncode == 1
    assert result.stderr.strip() == '{"error": "DATABASE_ERROR"}'
    assert not result.stdout


def test_missing_input_remains_input_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.cli.contests", str(tmp_path / "missing.json")],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert (
        result.returncode == 2
        and result.stderr.strip() == '{"error": "INPUT_UNAVAILABLE"}'
    )
