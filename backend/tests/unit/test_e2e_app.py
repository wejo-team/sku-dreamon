"""사전 검사 뒤 환경 파일·별칭이 바뀌어도 제품 서버가 개발 DB를 열지 못하게 한다."""

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from tests.e2e_app import create_app

DATABASE_URL = "postgresql+asyncpg://wejo:synthetic@127.0.0.1:55433/wejo_e2e"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in os.environ.copy():
        if name.upper() in {"DATABASE_URL", "OPENAI_API_KEY"}:
            monkeypatch.delenv(name)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "")


def test_uses_the_checked_settings_without_opening_a_database() -> None:
    app = create_app()
    assert make_url(str(app.state.settings.database_url)) == make_url(DATABASE_URL)


def test_rejects_lowercase_database_alias_added_after_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "database_url", "postgresql+asyncpg://wejo:synthetic@127.0.0.1:55432/wejo_dev"
    )
    with pytest.raises(RuntimeError, match="settings changed after verification"):
        create_app()


def test_rejects_a_different_test_database_after_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("database_url", DATABASE_URL.replace("wejo_e2e", "other_e2e"))
    with pytest.raises(RuntimeError, match="settings changed after verification"):
        create_app()


def test_rejects_development_database_at_server_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL.replace("wejo_e2e", "wejo_dev"))
    with pytest.raises(RuntimeError, match=r"localhost \*_e2e"):
        create_app()


def test_rejects_model_key_alias_added_after_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("openai_api_key", "synthetic-model-key")
    with pytest.raises(RuntimeError, match="settings changed after verification"):
        create_app()
