"""DB 연결 설정이 PostgreSQL의 asyncpg 드라이버만 허용하는지 검증한다."""

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
