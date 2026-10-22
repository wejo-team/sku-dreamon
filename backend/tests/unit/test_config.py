import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "url",
    ["sqlite+aiosqlite:///local.db", "postgresql://wejo:wejo@localhost/wejo"],
)
def test_database_url_requires_postgresql_asyncpg(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", url)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
