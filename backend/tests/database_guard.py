"""자동 검사에서 개발 DB 주소를 받지 않도록 전용 로컬 DB 이름을 확인한다."""

import re

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


def isolated_database_url(value: str, *, suffix: str) -> URL:
    """드라이버·호스트·DB 이름을 검증하고 접속 정보를 오류에 노출하지 않는다."""
    try:
        target = make_url(value)
        valid = (
            target.drivername == "postgresql+asyncpg"
            and target.host in {"localhost", "127.0.0.1", "::1"}
            and not target.query
            and target.database is not None
            and len(target.database) <= 63
            and re.fullmatch(r"[a-z][a-z0-9_]*" + re.escape(suffix), target.database)
        )
    except (ArgumentError, ValueError):
        valid = False
    if not valid:
        raise ValueError(
            f"Automatic tests require an explicit localhost *{suffix} PostgreSQL DB"
        ) from None
    return target
