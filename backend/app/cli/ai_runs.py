"""만료된 AI 실행 메타데이터를 정리하는 운영 명령을 제공한다."""

import asyncio

from app.core.config import Settings
from app.core.db.session import create_database
from app.services.ai_runs import RunService


async def cleanup() -> None:
    settings = Settings()
    database = create_database(str(settings.database_url))
    try:
        await RunService(database, settings).clean_expired()
        print("AI 실행 메타데이터 정리를 완료했습니다.")
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(cleanup())
