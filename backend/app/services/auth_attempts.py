"""인증 실패와 독립적으로 확정하는 15분 시도 제한을 적용한다."""

import hashlib
import math
from datetime import UTC, datetime, timedelta

from app.core.db.session import Database
from app.core.exceptions import AppError
from app.repositories import auth_attempts as repository

WINDOW = timedelta(minutes=15)


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def consume(database: Database, limits: list[tuple[str, int]]) -> None:
    keyed = sorted(
        (hashlib.sha256(key.encode()).hexdigest(), limit) for key, limit in limits
    )
    async with database.session() as session:
        try:
            rows = [
                (await repository.lock_attempt(session, key, _utcnow()), limit)
                for key, limit in keyed
            ]
            now = _utcnow()
            for row, limit in rows:
                if now >= row.window_started_at + WINDOW:
                    row.window_started_at, row.attempts = now, 0
                if row.attempts >= limit:
                    retry = max(
                        1,
                        math.ceil(
                            (row.window_started_at + WINDOW - now).total_seconds()
                        ),
                    )
                    raise AppError(
                        429,
                        "RATE_LIMITED",
                        "잠시 후 다시 시도해주세요.",
                        headers={"Retry-After": str(retry)},
                    )
            for row, _ in rows:
                row.attempts += 1
            await repository.flush(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
