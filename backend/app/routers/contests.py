"""접수 예정·진행·마감 공고의 원문 상세를 로그인 없이 제공한다."""

from typing import Annotated
from uuid import UUID

from fastapi import Path

from app.core.http.dependencies import DatabaseSession
from app.core.http.routers import BaseCrudRouter
from app.core.http.schemas import Success
from app.queries.contests import get_contest_detail
from app.schemas.contests import ContestDetail


async def get_contest(
    contest_id: Annotated[UUID, Path(alias="contestId")],
    session: DatabaseSession,
) -> ContestDetail:
    return await get_contest_detail(session, contest_id)


contests = BaseCrudRouter(prefix="/contests", tags=["contests"])
contests.add_detail(
    "/{contestId}",
    handler=get_contest,
    response_model=Success[ContestDetail],
    name="get_contest",
    summary="공모전 상세",
)
router = contests.router
