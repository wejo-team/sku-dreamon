"""로그인 없이 열람 가능한 팀 목록·모집글과 공고 하위 팀 목록을 제공한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, Success
from app.schemas.teams import AllTeamSearch, TeamDetail, TeamSearch, TeamSummary
from app.services.teams import get_team_detail, list_teams

router = APIRouter(tags=["teams"], responses=error_responses(422, 500, 503))


@router.get("/teams", summary="공개 팀 목록")
async def get_teams(
    session: DatabaseSession,
    search: Annotated[AllTeamSearch, Query()],
) -> Page[TeamSummary]:
    return await list_teams(session, search, contest_id=search.contest_id)


@router.get("/teams/{teamId}", summary="공개 모집글", responses=error_responses(404))
async def get_team(
    team_id: Annotated[UUID, Path(alias="teamId")],
    session: DatabaseSession,
) -> Success[TeamDetail]:
    return Success(data=await get_team_detail(session, team_id))


@router.get(
    "/contests/{contestId}/teams",
    summary="공고의 공개 팀 목록",
    responses=error_responses(404),
)
async def get_contest_teams(
    contest_id: Annotated[UUID, Path(alias="contestId")],
    session: DatabaseSession,
    search: Annotated[TeamSearch, Query()],
) -> Page[TeamSummary]:
    return await list_teams(
        session, search, contest_id=contest_id, require_contest=True
    )
