"""FastAPI 의존성 주입으로 요청 범위에 DB 세션을 제공한다."""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import Database


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database = cast(Database, request.app.state.database)
    async with database.session() as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
