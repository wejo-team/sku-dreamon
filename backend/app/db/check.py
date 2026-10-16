import asyncio

from sqlalchemy import text

from app.core.config import Settings
from app.db.session import create_database


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
