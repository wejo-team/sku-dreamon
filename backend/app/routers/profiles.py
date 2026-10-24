"""인증된 본인 프로필과 공개 사람 목록·상세의 읽기 API를 제공한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, Success
from app.dependencies.auth import CurrentAccount
from app.dependencies.csrf import require_csrf
from app.schemas.profile_write import ProfileWrite, VisibilityWrite
from app.schemas.profiles import PeopleQuery, PersonSummary, ProfileResponse
from app.services import profile_write as commands
from app.services import profiles as service

router = APIRouter(tags=["profiles"], responses=error_responses(401, 422, 500, 503))


@router.put(
    "/me/profile",
    response_model=Success[ProfileResponse],
    responses=error_responses(403, 409),
)
async def save_profile(
    account_id: CurrentAccount,
    session: DatabaseSession,
    body: ProfileWrite,
    response: Response,
    csrf: Annotated[None, Depends(require_csrf)],
) -> Success[ProfileResponse]:
    result = await commands.save_profile(session, account_id, body)
    response.headers["Cache-Control"] = "no-store"
    return Success(data=result)


@router.put(
    "/me/profile/visibility",
    response_model=Success[ProfileResponse],
    responses=error_responses(403, 404, 409),
)
async def set_visibility(
    account_id: CurrentAccount,
    session: DatabaseSession,
    body: VisibilityWrite,
    response: Response,
    csrf: Annotated[None, Depends(require_csrf)],
) -> Success[ProfileResponse]:
    result = await commands.set_visibility(session, account_id, body)
    response.headers["Cache-Control"] = "no-store"
    return Success(data=result)


@router.get("/me/profile", responses=error_responses(404))
async def get_own_profile(
    account_id: CurrentAccount, session: DatabaseSession
) -> Success[ProfileResponse]:
    return Success(data=await service.get_own_profile(session, account_id))


@router.get("/people")
async def list_people(
    account_id: CurrentAccount,
    session: DatabaseSession,
    query: Annotated[PeopleQuery, Query()],
) -> Page[PersonSummary]:
    return await service.list_people(session, query)


@router.get("/people/{accountId}", responses=error_responses(404))
async def get_public_profile(
    current_account_id: CurrentAccount,
    session: DatabaseSession,
    account_id: Annotated[UUID, Path(alias="accountId")],
) -> Success[ProfileResponse]:
    return Success(data=await service.get_public_profile(session, account_id))
