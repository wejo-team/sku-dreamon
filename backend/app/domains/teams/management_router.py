"""내 팀·현재 팀 공간과 팀장의 명시적 모집 변경 경로를 제공한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Response

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, Success
from app.domains.auth.dependencies import CurrentAccount
from app.domains.teams import membership_queries
from app.domains.teams.management_schemas import (
    TeamSpace,
    WorkspaceSearch,
    WorkspaceTeam,
)

router = APIRouter(tags=["team-management"])
_read_errors = error_responses(401, 403, 404, 422, 500, 503)


@router.get("/me/teams", response_model=Page[WorkspaceTeam], responses=_read_errors)
async def list_my_teams(
    account: CurrentAccount,
    session: DatabaseSession,
    response: Response,
    query: Annotated[WorkspaceSearch, Query()],
) -> Page[WorkspaceTeam]:
    response.headers["Cache-Control"] = "no-store"
    return await membership_queries.list_workspace_teams(
        session, account, page=query.page, page_size=query.page_size
    )


@router.get(
    "/teams/{teamId}/space", response_model=Success[TeamSpace], responses=_read_errors
)
async def get_space(
    team_id: Annotated[UUID, Path(alias="teamId")],
    account: CurrentAccount,
    session: DatabaseSession,
    response: Response,
) -> Success[TeamSpace]:
    response.headers["Cache-Control"] = "no-store"
    return Success(
        data=await membership_queries.get_team_space(session, team_id, account)
    )
