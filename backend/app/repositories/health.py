"""준비 검사에 필요한 최소 DB 왕복과 Alembic revision만 읽는다."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def probe_database(session: AsyncSession) -> frozenset[str]:
    await session.execute(text("SELECT 1"))
    versions = await session.scalars(text("SELECT version_num FROM alembic_version"))
    return frozenset(versions.all())
