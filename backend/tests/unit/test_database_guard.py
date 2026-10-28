"""잘못 지정한 자동 검사 대상이 연결 전에 거부되는지 확인한다."""

import pytest

from tests.database_guard import isolated_database_url
from tests.integration.conftest import configured_database_url


@pytest.mark.parametrize("suffix", ["_test", "_e2e"])
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_accepts_explicit_isolated_database(suffix: str, host: str) -> None:
    target = isolated_database_url(
        f"postgresql+asyncpg://wejo:wejo@{host}:55433/wejo{suffix}", suffix=suffix
    )
    assert target.database == f"wejo{suffix}"


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+asyncpg://wejo:private@127.0.0.1/wejo_dev",
        "postgresql+asyncpg://wejo:private@127.0.0.1/wejo",
        "postgresql+asyncpg://wejo:private@db.example.com/wejo_e2e",
        "postgresql+asyncpg://wejo:private@127.0.0.1/wejo_e2e?host=remote",
        "postgresql+asyncpg://wejo:private@/wejo_e2e",
        "postgresql+asyncpg://wejo:private@127.0.0.1/",
        "postgresql+asyncpg://wejo:private@127.0.0.1/a%2Fe2e_e2e",
        "postgresql+asyncpg://wejo:private@127.0.0.1/" + "a" * 64 + "_e2e",
        "postgresql://wejo:private@127.0.0.1/wejo_e2e",
        "sqlite:///wejo_e2e",
        "not-a-url-private",
    ],
)
def test_rejects_unsafe_targets_without_leaking_credentials(value: str) -> None:
    with pytest.raises(ValueError) as raised:
        isolated_database_url(value, suffix="_e2e")
    assert "private" not in str(raised.value)


def test_pytest_rejects_development_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://wejo:wejo@127.0.0.1/wejo_dev"
    )
    with pytest.raises(pytest.fail.Exception, match=r"localhost \*_test"):
        configured_database_url()


def test_pytest_does_not_accept_browser_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://wejo:wejo@127.0.0.1/wejo_e2e"
    )
    with pytest.raises(pytest.fail.Exception, match=r"localhost \*_test"):
        configured_database_url()


def test_pytest_keeps_no_database_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    with pytest.raises(pytest.skip.Exception):
        configured_database_url()
