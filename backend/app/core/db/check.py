"""설정된 PostgreSQL 연결을 확인하고 검사에 사용한 엔진을 정리한다."""

import asyncio

from sqlalchemy import text

from app.core.config import Settings
from app.core.db.session import create_database


async def check_connection() -> None:
    database = create_database(str(Settings().database_url))
    try:
        async with database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        print("PostgreSQL connection OK")
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_connection())
