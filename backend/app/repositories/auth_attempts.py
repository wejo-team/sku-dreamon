"""시도 제한 키의 생성·행 잠금으로 동시 요청의 집계를 직렬화한다."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_attempts import AuthAttempt


async def lock_attempt(session: AsyncSession, key: str, now: datetime) -> AuthAttempt:
    await session.execute(
        insert(AuthAttempt)
        .values(key=key, window_started_at=now, attempts=0)
        .on_conflict_do_nothing(index_elements=[AuthAttempt.key])
    )
    row = await session.scalar(
        select(AuthAttempt)
        .where(AuthAttempt.key == key)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def flush(session: AsyncSession) -> None:
    await session.flush()
